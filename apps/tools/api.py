from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import ToolUsageLog
from .serializers import ToolUsageLogSerializer
from .utils import DeepSeekClient
import tempfile
import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from django.conf import settings
from django.core.files import File
import logging
import re
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)


class GenerateTestCasesAPI(APIView):
    permission_classes = [IsAuthenticated]

    # 提示词模板调整为匹配目标格式
    DEFAULT_PROMPT = """作为资深测试工程师，请根据以下产品需求生成全面的测试用例，格式要求如下：
1. 使用#号层级结构组织模块（# 一级模块，## 二级功能，### 三级子功能）
2. 每个测试用例包含：
   - 测试ID（格式：XXX_001）
   - 测试场景
   - 前置条件（可包含列表项）
   - 测试步骤（可包含列表项）
   - 预期结果（可包含列表项）
   - 重要程度
3. 测试用例使用####标记开头

产品需求：{requirement}"""

    def post(self, request):
        try:
            start_time = datetime.now()
            requirement = request.data.get('requirement', '').strip()
            user_prompt = request.data.get('prompt', '').strip()

            logger.info(
                f"用户 {request.user.username} 发起测试用例生成请求，"
                f"需求长度: {len(requirement)}，"
                f"时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if not requirement:
                logger.warning("测试用例生成请求缺少requirement参数")
                return Response(
                    {'error': '请输入产品需求内容'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 处理文件名
            truncated_req = requirement[:20].strip() if requirement else "default"
            invalid_chars = r'[\\/*?:"<>| ]'
            cleaned_req = re.sub(invalid_chars, '_', truncated_req)
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            outfile_name = f"{cleaned_req}_{current_time}.mm"

            final_prompt = user_prompt if user_prompt else self.DEFAULT_PROMPT.format(requirement=requirement)

            # 调用DeepSeek API生成测试用例
            try:
                deepseek = DeepSeekClient()
                raw_response = deepseek.generate_test_cases(requirement, final_prompt)

                # 终端打印完整响应
                print("\n" + "=" * 80)
                print("DeepSeek API完整返回内容:")
                print("-" * 80)
                print(raw_response)
                print("-" * 80 + "\n")

                if not raw_response:
                    raise ValueError("未从API获取到有效响应")
            except Exception as e:
                logger.error(f"DeepSeek API调用失败: {str(e)}", exc_info=True)
                return Response(
                    {'error': f'AI接口调用失败: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # 解析API响应（适配微信红包测试用例格式）
            test_cases = self._parse_test_cases(raw_response)

            # 确保输出目录存在
            output_dir = os.path.join(settings.MEDIA_ROOT, 'tool_outputs')
            os.makedirs(output_dir, exist_ok=True)

            # 创建FreeMind格式文件
            with tempfile.NamedTemporaryFile(suffix='.mm', delete=False, mode='w', encoding='utf-8') as tmp:
                mindmap_xml = self._generate_freemind(test_cases)
                tmp.write(mindmap_xml)
                tmp.flush()

                # 保存到模型
                log = ToolUsageLog.objects.create(
                    user=request.user,
                    tool_type='TEST_CASE',
                    input_data=json.dumps({
                        'requirement': requirement,
                        'prompt': final_prompt
                    })
                )

                with open(tmp.name, 'rb') as f:
                    log.output_file.save(outfile_name, File(f), save=True)

                os.unlink(tmp.name)

            # 验证文件是否成功保存
            saved_file_path = os.path.join(output_dir, outfile_name)
            if os.path.exists(saved_file_path):
                logger.info(f"用户 {request.user.username} 测试用例生成成功，文件: {saved_file_path}")
            else:
                logger.warning(f"用户 {request.user.username} 测试用例生成成功，但文件未找到: {saved_file_path}")

            return Response({
                'download_url': f'/tools/download/{outfile_name}',
                'log_id': log.id,
                'raw_response': raw_response,
                'structured_test_cases': test_cases
            })

        except Exception as e:
            logger.error(
                f"用户 {request.user.username} 测试用例生成失败，"
                f"耗时: {(datetime.now() - start_time).total_seconds()}秒，"
                f"错误: {str(e)}",
                exc_info=True
            )

            return Response(
                {'error': f'服务器处理失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _clean_text(self, text):
        """清除特殊字符但保留必要格式"""
        # 清除Markdown粗体标记(**)
        cleaned = re.sub(r'\*\*', '', text)
        # 清除多余空格
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_test_cases(self, raw_response):
        """解析微信红包测试用例格式，保持层级结构"""
        parsed_data = {
            "title": "测试用例集",
            "levels": []  # 存储一级模块
        }

        # 按行分割内容
        lines = [line.rstrip('\n') for line in raw_response.splitlines()]
        current_level1 = None  # 一级模块（# 开头）
        current_level2 = None  # 二级功能（## 开头）
        current_level3 = None  # 三级子功能（### 开头）
        current_case = None  # 当前测试用例
        current_field = None  # 当前字段（测试场景、前置条件等）

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

            # 1. 识别一级模块（# 开头）
            if line.startswith('# ') and not line.startswith('##'):
                # 重置所有下级结构
                current_level1 = {
                    "title": self._clean_text(line[2:].strip()),
                    "level2": []
                }
                parsed_data["levels"].append(current_level1)
                current_level2 = None
                current_level3 = None
                current_case = None
                continue

            # 2. 识别二级功能（## 开头）
            if line.startswith('## ') and not line.startswith('###') and current_level1:
                current_level2 = {
                    "title": self._clean_text(line[3:].strip()),
                    "level3": []
                }
                current_level1["level2"].append(current_level2)
                current_level3 = None
                current_case = None
                continue

            # 3. 识别三级子功能（### 开头）
            if line.startswith('### ') and current_level2:
                current_level3 = {
                    "title": self._clean_text(line[4:].strip()),
                    "cases": []
                }
                current_level2["level3"].append(current_level3)
                current_case = None
                continue

            # 4. 识别测试用例（#### 开头）
            if line.startswith('####') and current_level3:
                # 保存上一个测试用例
                if current_case:
                    current_level3["cases"].append(current_case)

                # 初始化新测试用例
                current_case = {
                    "test_id": "",
                    "测试场景": "",
                    "前置条件": [],
                    "测试步骤": [],
                    "预期结果": [],
                    "重要程度": ""
                }

                # 提取测试ID
                case_title = self._clean_text(line[4:].strip())
                id_match = re.match(r'^测试ID:\s*([A-Za-z0-9_]+)', case_title)
                if id_match:
                    current_case["test_id"] = id_match.group(1)
                else:
                    # 尝试从标题中提取ID（如WXHB_001）
                    id_candidate = re.search(r'[A-Z]+_\d+', case_title)
                    if id_candidate:
                        current_case["test_id"] = id_candidate.group()
                continue

            # 5. 处理测试用例字段
            if current_case:
                # 识别字段标题（测试场景、前置条件等）
                field_match = re.match(
                    r'^(测试场景|前置条件|测试步骤|预期结果|重要程度)\s*[:：]\s*(.*)$',
                    stripped_line
                )

                if field_match:
                    current_field = field_match.group(1)
                    field_content = self._clean_text(field_match.group(2))

                    # 处理有初始内容的字段
                    if field_content:
                        if current_field in ['前置条件', '测试步骤', '预期结果']:
                            current_case[current_field].append(field_content)
                        else:
                            current_case[current_field] = field_content
                    continue

                # 处理列表项（数字+点号开头）
                list_item_match = re.match(r'^\d+\.\s*(.*)$', stripped_line)
                if list_item_match and current_field in ['前置条件', '测试步骤', '预期结果']:
                    item_content = self._clean_text(list_item_match.group(1))
                    current_case[current_field].append(item_content)
                    continue

                # 处理字段的延续内容
                if current_field and stripped_line:
                    cleaned_line = self._clean_text(stripped_line)
                    if current_field in ['前置条件', '测试步骤', '预期结果']:
                        current_case[current_field].append(cleaned_line)
                    else:
                        current_case[current_field] += " " + cleaned_line

        # 添加最后一个测试用例
        if current_case and current_level3 and current_case not in current_level3["cases"]:
            current_level3["cases"].append(current_case)

        # 处理没有解析到任何内容的情况
        if not parsed_data["levels"]:
            parsed_data["levels"].append({
                "title": "默认模块",
                "level2": [{
                    "title": "默认功能",
                    "level3": [{
                        "title": "默认子功能",
                        "cases": [{
                            "test_id": "DEFAULT_001",
                            "测试场景": "未解析到有效测试用例",
                            "前置条件": [],
                            "测试步骤": [],
                            "预期结果": [],
                            "重要程度": "中"
                        }]
                    }]
                }]
            })

        return parsed_data

    def _generate_freemind(self, test_cases):
        """生成与测试用例层级匹配的FreeMind XML"""
        ET.register_namespace('', 'http://freemind.sourceforge.net/wiki/index.php/XML')

        map_root = ET.Element("map")
        map_root.set("version", "1.0.1")

        # 根节点
        root_topic = ET.SubElement(map_root, "node")
        root_topic.set("TEXT", test_cases["title"])
        root_topic.set("STYLE", "bubble")
        root_topic.set("COLOR", "#000000")

        # 一级模块（# 标题）
        for level1 in test_cases["levels"]:
            level1_node = ET.SubElement(root_topic, "node")
            level1_node.set("TEXT", level1["title"])
            level1_node.set("COLOR", "#FF5733")  # 一级节点颜色
            level1_node.set("STYLE", "fork")

            # 二级功能（## 标题）
            for level2 in level1["level2"]:
                level2_node = ET.SubElement(level1_node, "node")
                level2_node.set("TEXT", level2["title"])
                level2_node.set("COLOR", "#33FF57")  # 二级节点颜色
                level2_node.set("STYLE", "fork")

                # 三级子功能（### 标题）
                for level3 in level2["level3"]:
                    level3_node = ET.SubElement(level2_node, "node")
                    level3_node.set("TEXT", level3["title"])
                    level3_node.set("COLOR", "#3357FF")  # 三级节点颜色
                    level3_node.set("STYLE", "fork")

                    # 测试用例
                    for case in level3["cases"]:
                        case_node = ET.SubElement(level3_node, "node")
                        case_title = f"{case['test_id']}" if case['test_id'] else "未命名用例"
                        case_node.set("TEXT", case_title)
                        case_node.set("COLOR", "#FF33F5")  # 用例节点颜色
                        case_node.set("STYLE", "bullet")

                        # 测试场景
                        if case["测试场景"]:
                            scene_node = ET.SubElement(case_node, "node")
                            scene_node.set("TEXT", f"测试场景: {case['测试场景']}")
                            scene_node.set("COLOR", "#696969")

                        # 前置条件
                        if case["前置条件"]:
                            precondition_node = ET.SubElement(case_node, "node")
                            precondition_node.set("TEXT", "前置条件")
                            precondition_node.set("COLOR", "#696969")

                            for idx, item in enumerate(case["前置条件"], 1):
                                item_node = ET.SubElement(precondition_node, "node")
                                item_node.set("TEXT", f"{idx}. {item}")

                        # 测试步骤
                        if case["测试步骤"]:
                            steps_node = ET.SubElement(case_node, "node")
                            steps_node.set("TEXT", "测试步骤")
                            steps_node.set("COLOR", "#696969")

                            for idx, item in enumerate(case["测试步骤"], 1):
                                item_node = ET.SubElement(steps_node, "node")
                                item_node.set("TEXT", f"{idx}. {item}")

                        # 预期结果
                        if case["预期结果"]:
                            expected_node = ET.SubElement(case_node, "node")
                            expected_node.set("TEXT", "预期结果")
                            expected_node.set("COLOR", "#696969")

                            for idx, item in enumerate(case["预期结果"], 1):
                                item_node = ET.SubElement(expected_node, "node")
                                item_node.set("TEXT", f"{idx}. {item}")

                        # 重要程度
                        if case["重要程度"]:
                            importance_node = ET.SubElement(case_node, "node")
                            importance_node.set("TEXT", f"重要程度: {case['重要程度']}")
                            importance_node.set("COLOR", "#696969")

        # 格式化XML
        rough_string = ET.tostring(map_root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return '\n'.join([line for line in reparsed.toprettyxml(indent="  ").split('\n') if line.strip()])
