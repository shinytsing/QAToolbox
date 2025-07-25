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

    # 保留详细字段同时维持指定格式
    DEFAULT_PROMPT = """根据以下产品需求生成全球化APP测试用例集，需遵循指定格式:
{requirement}

## 输出格式要求
1. 测试用例以标题为分割，格式为：**测试ID 测试标题**
2. 每个测试用例包含以下字段，使用层级列表：
   - 场景：描述测试场景
   - 前置条件：执行前的系统状态
   - 前置条件不满足时的预期结果：前置条件不满足时的系统表现
   - 测试目的：验证的功能点或场景
   - 测试环境：设备/系统/网络环境
   - 测试数据：含正常值/边界值/异常值
   - 测试步骤：编号列出，每个步骤后紧跟其预期结果
     1. 步骤内容
        预期结果：具体结果描述1
        预期结果：具体结果描述2
     2. 步骤内容
        预期结果：具体结果描述1
   - 重要程度：高/中/低
   - 测试类型：标记所属类型(可多选)

3. 按功能模块组织，使用## 标记模块

## 示例格式
## 红包功能模块
**TC-020 多语言红包测试**
    - 场景：非中文环境下使用红包
    - 前置条件：设置微信为英文
    - 前置条件不满足时的预期结果：系统提示需要切换到英文环境
    - 测试目的：验证多语言环境下红包功能的正确性
    - 测试环境：iOS 16.0，网络环境良好
    - 测试数据：20元红包，英文系统语言
    - 测试步骤：
        1. 发送红包
            预期结果：1. 所有文本正确翻译
            预期结果：2. 功能正常
        2. 查看界面文本
            预期结果：1. 所有文本正确翻译
            预期结果：2. 功能正常
    - 重要程度：低
    - 测试类型：国际化测试,功能测试"""

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

            truncated_req = requirement[:20].strip() if requirement else "default"
            invalid_chars = r'[\\/*?:"<>| ]'
            cleaned_req = re.sub(invalid_chars, '_', truncated_req)
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            outfile_name = f"{cleaned_req}_{current_time}.mm"

            final_prompt = user_prompt if user_prompt else self.DEFAULT_PROMPT.format(requirement=requirement)

            try:
                deepseek = DeepSeekClient()
                raw_response = deepseek.generate_test_cases(requirement, final_prompt)
                logger.info("DeepSeek API返回原始数据:")
                logger.info(raw_response)

                if not raw_response:
                    raise ValueError("未从API获取到有效响应")
            except Exception as e:
                logger.error(f"DeepSeek API调用失败: {str(e)}", exc_info=True)
                return Response(
                    {'error': f'AI接口调用失败: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # 解析测试用例，同时保留原始响应
            test_cases = self._parse_test_cases(raw_response)
            # 确保原始响应被保存
            test_cases['raw_response'] = raw_response

            output_dir = os.path.join(settings.MEDIA_ROOT, 'tool_outputs')
            os.makedirs(output_dir, exist_ok=True)

            with tempfile.NamedTemporaryFile(suffix='.mm', delete=False, mode='w', encoding='utf-8') as tmp:
                mindmap_xml = self._generate_freemind(test_cases)
                tmp.write(mindmap_xml)
                tmp.flush()

                log = ToolUsageLog.objects.create(
                    user=request.user,
                    tool_type='TEST_CASE',
                    input_data=json.dumps({
                        'requirement': requirement,
                        'prompt': final_prompt
                    }),
                    # 存储原始响应到数据库
                    raw_response=raw_response
                )

                with open(tmp.name, 'rb') as f:
                    log.output_file.save(outfile_name, File(f), save=True)

                os.unlink(tmp.name)

            saved_file_path = os.path.join(output_dir, outfile_name)
            if os.path.exists(saved_file_path):
                logger.info(f"用户 {request.user.username} 测试用例生成成功，文件: {saved_file_path}")
            else:
                logger.warning(f"用户 {request.user.username} 测试用例生成成功，但文件未找到: {saved_file_path}")

            return Response({
                'download_url': f'/tools/download/{outfile_name}',
                'log_id': log.id,
                'raw_response': raw_response,  # 返回原始响应
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

    def _parse_test_cases(self, raw_response):
        """增强解析逻辑，优先确保保留所有原始内容"""
        print("DeepSeek返回的原始测试用例:")
        print(raw_response)

        # 首先保存完整的原始响应
        structured_data = {
            "title": "AI生成测试用例",
            "original_content": raw_response,  # 保存完整原始内容
            "modules": {},  # 按模块组织
            "unparsed_sections": []  # 存储无法解析的完整段落
        }

        # 按段落分割内容，而不是按行，减少内容碎片化
        paragraphs = re.split(r'\n\s*\n', raw_response.strip())
        current_module = None
        current_case = None

        # 先尝试整体解析
        for para in paragraphs:
            if not para.strip():
                continue

            # 处理模块 (## 标题)
            if para.strip().startswith('## '):
                # 保存上一个用例
                if current_case and current_module:
                    structured_data["modules"][current_module]["cases"].append(current_case)

                module_name = para.strip()[3:].strip()
                current_module = module_name
                structured_data["modules"][module_name] = {
                    "name": module_name,
                    "original_content": para,  # 保存模块原始内容
                    "cases": []
                }
                current_case = None
                continue

            # 处理测试用例标题 (**开头)
            if para.strip().startswith('**') and para.strip().endswith('**') and current_module:
                # 保存上一个用例
                if current_case:
                    structured_data["modules"][current_module]["cases"].append(current_case)

                # 提取测试ID和标题
                case_header = para.strip()[2:-2].strip()
                test_id = ""
                test_title = case_header

                id_match = re.match(r'^([A-Z0-9-]+)\s+(.*)$', case_header)
                if id_match:
                    test_id = id_match.group(1)
                    test_title = id_match.group(2)

                # 初始化新测试用例，包含所有必要字段和原始内容
                current_case = {
                    "测试ID": test_id,
                    "测试标题": test_title,
                    "original_content": para,  # 保存用例原始内容
                    "测试场景": "",
                    "前置条件": "",
                    "前置条件不满足时的预期结果": "",
                    "测试目的": "",
                    "测试环境": "",
                    "测试数据": "",
                    "测试步骤": [],  # 包含预期结果的字典列表
                    "重要程度": "",
                    "测试类型": [],
                    "unparsed_lines": []  # 存储用例中无法解析的行
                }
                continue

            # 处理用例内容
            if current_case:
                # 按行解析段落内的内容
                self._parse_case_paragraph(para, current_case)
                continue

            # 无法关联到任何模块或用例的内容
            structured_data["unparsed_sections"].append(para)

        # 添加最后一个用例
        if current_case and current_module:
            structured_data["modules"][current_module]["cases"].append(current_case)

        # 处理没有解析到任何模块的情况
        if not structured_data["modules"]:
            structured_data["modules"]["默认模块"] = {
                "name": "默认模块",
                "original_content": raw_response,
                "cases": [{
                    "测试ID": "DEFAULT-001",
                    "测试标题": "默认测试用例",
                    "original_content": raw_response,
                    "测试场景": "未解析到结构化测试用例",
                    "前置条件": "",
                    "前置条件不满足时的预期结果": "",
                    "测试目的": "",
                    "测试环境": "",
                    "测试数据": "",
                    "测试步骤": [],
                    "重要程度": "中",
                    "测试类型": ["功能测试"],
                    "unparsed_lines": raw_response.split('\n')  # 保存原始内容
                }]
            }

        # 打印结构化后的测试用例
        print("\n结构化后的测试用例:")
        import pprint
        pprint.pprint(structured_data)

        return structured_data

    def _parse_case_paragraph(self, paragraph, current_case):
        """解析用例段落中的内容，尽可能结构化同时保留无法解析的部分"""
        current_field = None
        current_step = None
        line_buffer = []

        for line in paragraph.split('\n'):
            stripped_line = line.strip()
            indent_level = len(line) - len(line.lstrip())

            if not stripped_line:
                if line_buffer:
                    self._process_line_buffer(line_buffer, current_case, current_field, current_step)
                    line_buffer = []
                continue

            # 尝试匹配已知字段
            field_match = re.match(
                r'^-?\s*(场景|前置条件|前置条件不满足时的预期结果|测试目的|测试环境|测试数据|重要程度|测试类型)\s*[:：]\s*(.*)$',
                stripped_line)

            if field_match:
                if line_buffer:
                    self._process_line_buffer(line_buffer, current_case, current_field, current_step)
                    line_buffer = []

                current_field = field_match.group(1)
                field_value = field_match.group(2).strip()

                # 字段映射
                field_mapping = {
                    "场景": "测试场景",
                    "前置条件": "前置条件",
                    "前置条件不满足时的预期结果": "前置条件不满足时的预期结果",
                    "测试目的": "测试目的",
                    "测试环境": "测试环境",
                    "测试数据": "测试数据",
                    "重要程度": "重要程度",
                    "测试类型": "测试类型"
                }

                internal_field = field_mapping.get(current_field)
                if internal_field:
                    if internal_field == "测试类型":
                        current_case[internal_field] = [t.strip() for t in re.split(r'[,，]', field_value) if t.strip()]
                    else:
                        current_case[internal_field] = field_value

                current_step = None  # 重置步骤跟踪
                continue

            # 处理测试步骤 (数字. 开头)
            step_match = re.match(r'^(\d+)\.\s+(.*)$', stripped_line)
            if step_match and indent_level > 4:
                if line_buffer:
                    self._process_line_buffer(line_buffer, current_case, current_field, current_step)
                    line_buffer = []

                step_content = step_match.group(2).strip()
                current_step = {
                    "步骤": step_content,
                    "预期结果": [],
                    "unparsed_lines": []  # 步骤中无法解析的内容
                }
                current_case["测试步骤"].append(current_step)
                current_field = "测试步骤"
                continue

            # 处理预期结果 (预期结果: 开头)
            expected_match = re.match(r'^预期结果[:：]\s*(.*)$', stripped_line)
            if expected_match and current_step and current_field == "测试步骤":
                expected_result = expected_match.group(1).strip()
                current_step["预期结果"].append(expected_result)
                continue

            # 无法立即解析的内容加入缓冲
            line_buffer.append(line)

        # 处理剩余的缓冲内容
        if line_buffer:
            self._process_line_buffer(line_buffer, current_case, current_field, current_step)

    def _process_line_buffer(self, buffer, current_case, current_field, current_step):
        """处理缓冲的行内容，尽可能归类或保存为额外内容"""
        if not current_case:
            return

        # 将缓冲内容合并为文本
        buffer_text = '\n'.join([line.strip() for line in buffer if line.strip()])

        if not buffer_text:
            return

        # 尝试将内容归类到当前字段
        if current_field and current_field != "测试步骤":
            # 追加到当前字段
            current_case_field = {
                "场景": "测试场景",
                "前置条件": "前置条件",
                "前置条件不满足时的预期结果": "前置条件不满足时的预期结果",
                "测试目的": "测试目的",
                "测试环境": "测试环境",
                "测试数据": "测试数据",
                "重要程度": "重要程度",
                "测试类型": "测试类型"
            }.get(current_field)

            if current_case_field:
                if current_case_field == "测试类型":
                    types = [t.strip() for t in re.split(r'[,，]', buffer_text) if t.strip()]
                    current_case[current_case_field].extend(types)
                else:
                    current_case[current_case_field] += "\n" + buffer_text
                return

        # 如果是测试步骤中的内容
        if current_field == "测试步骤" and current_step:
            # 检查是否是预期结果
            if buffer_text.startswith("预期结果"):
                expected_match = re.match(r'^预期结果[:：]\s*(.*)$', buffer_text)
                if expected_match:
                    current_step["预期结果"].append(expected_match.group(1).strip())
                    return
                else:
                    current_step["unparsed_lines"].append(buffer_text)
                    return
            # 否则作为步骤补充内容
            current_step["步骤"] += "\n" + buffer_text
            return

        # 无法归类的内容保存到用例的未解析行中
        current_case["unparsed_lines"].append(buffer_text)

    def _generate_freemind(self, test_cases):
        """生成FreeMind XML，包含所有字段和原始内容"""
        ET.register_namespace('', 'http://freemind.sourceforge.net/wiki/index.php/XML')

        map_root = ET.Element("map")
        map_root.set("version", "1.0.1")

        root_topic = ET.SubElement(map_root, "node")
        root_topic.set("TEXT", test_cases["title"])
        root_topic.set("STYLE", "bubble")
        root_topic.set("COLOR", "#000000")

        # 添加完整原始响应节点
        raw_node = ET.SubElement(root_topic, "node")
        raw_node.set("TEXT", "完整原始响应")
        raw_node.set("COLOR", "#808080")
        # 按段落展示原始响应
        for para in re.split(r'\n\s*\n', test_cases["original_content"].strip()):
            if para.strip():
                para_node = ET.SubElement(raw_node, "node")
                para_node.set("TEXT", para.strip()[:150] + ("..." if len(para) > 150 else ""))

        # 添加未解析段落节点（如果有）
        if test_cases["unparsed_sections"]:
            unparsed_node = ET.SubElement(root_topic, "node")
            unparsed_node.set("TEXT", "未解析段落")
            unparsed_node.set("COLOR", "#FF0000")
            for section in test_cases["unparsed_sections"]:
                section_node = ET.SubElement(unparsed_node, "node")
                section_node.set("TEXT", section.strip()[:100] + ("..." if len(section) > 100 else ""))

        for module_name, module_data in test_cases["modules"].items():
            module_node = ET.SubElement(root_topic, "node")
            module_node.set("TEXT", module_name)
            module_node.set("COLOR", "#FF7F50")
            module_node.set("STYLE", "fork")

            # 添加模块原始内容
            module_raw_node = ET.SubElement(module_node, "node")
            module_raw_node.set("TEXT", "模块原始内容")
            module_raw_node.set("COLOR", "#808080")
            module_raw_node.set("TEXT", module_data["original_content"].strip()[:100] + (
                "..." if len(module_data["original_content"]) > 100 else ""))

            for case in module_data["cases"]:
                self._add_case_to_node(module_node, case)

        rough_string = ET.tostring(map_root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return '\n'.join([line for line in reparsed.toprettyxml(indent="  ").split('\n') if line.strip()])

    def _add_case_to_node(self, parent_node, case):
        """将测试用例添加到节点，包含所有字段和原始内容"""
        case_node = ET.SubElement(parent_node, "node")
        case_title = f"{case['测试ID']}: {case['测试标题']}" if case['测试ID'] else case['测试标题']
        case_node.set("TEXT", case_title)
        case_node.set("COLOR", "#4682B4")
        case_node.set("STYLE", "bullet")

        # 添加用例原始内容
        case_raw_node = ET.SubElement(case_node, "node")
        case_raw_node.set("TEXT", "用例原始内容")
        case_raw_node.set("COLOR", "#808080")
        case_raw_node.set("TEXT", case["original_content"].strip()[:100] + (
            "..." if len(case["original_content"]) > 100 else ""))

        # 添加所有字段
        fields = [
            ("测试场景", case["测试场景"]),
            ("前置条件", case["前置条件"]),
            ("前置条件不满足时的预期结果", case["前置条件不满足时的预期结果"]),
            ("测试目的", case["测试目的"]),
            ("测试环境", case["测试环境"]),
            ("测试数据", case["测试数据"]),
            ("重要程度", case["重要程度"]),
            ("测试类型", ", ".join(case["测试类型"]))
        ]

        for field_name, field_value in fields:
            if field_value:
                field_node = ET.SubElement(case_node, "node")
                field_node.set("TEXT", f"{field_name}: {field_value}")
                field_node.set("COLOR", "#696969")

        # 添加测试步骤及对应的预期结果
        if case["测试步骤"]:
            steps_node = ET.SubElement(case_node, "node")
            steps_node.set("TEXT", "测试步骤与预期结果")
            steps_node.set("COLOR", "#8B4513")

            for step in case["测试步骤"]:
                step_node = ET.SubElement(steps_node, "node")
                step_node.set("TEXT", f"步骤: {step['步骤']}")
                step_node.set("COLOR", "#8B4513")

                for i, expected in enumerate(step["预期结果"], 1):
                    expected_node = ET.SubElement(step_node, "node")
                    expected_node.set("TEXT", f"预期结果 {i}: {expected}")
                    expected_node.set("COLOR", "#228B22")

                # 步骤中的未解析内容
                if step["unparsed_lines"]:
                    step_unparsed = ET.SubElement(step_node, "node")
                    step_unparsed.set("TEXT", "步骤未解析内容")
                    step_unparsed.set("COLOR", "#FFA500")
                    for line in step["unparsed_lines"]:
                        line_node = ET.SubElement(step_unparsed, "node")
                        line_node.set("TEXT", line[:100])

        # 添加用例级别的未解析内容
        if case["unparsed_lines"]:
            extra_node = ET.SubElement(case_node, "node")
            extra_node.set("TEXT", "用例未解析内容")
            extra_node.set("COLOR", "#FFA500")
            for content in case["unparsed_lines"]:
                content_node = ET.SubElement(extra_node, "node")
                content_node.set("TEXT", content[:100])
