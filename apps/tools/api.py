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

    # 默认提示词模板（当用户未提供时使用）
    DEFAULT_PROMPT = """作为资深测试工程师，请根据以下产品需求生成全面的测试用例：
1. 涵盖功能测试、边界测试、异常测试场景
2. 每个测试用例需包含：测试场景、前置条件、操作步骤、预期结果
3. 按模块或功能点分类组织（使用# 标题作为分类）
4. 需考虑用户可能的误操作和极端情况
产品需求：{requirement}"""

    def post(self, request):
        try:
            start_time = datetime.now()
            # 1. 获取并验证请求参数
            requirement = request.data.get('requirement', '').strip()
            user_prompt = request.data.get('prompt', '').strip()

            logger.info(
                f"用户 {request.user.username} 发起测试用例生成请求，"
                f"需求长度: {len(requirement)}，"
                f"时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # 验证需求参数
            if not requirement:
                logger.warning("测试用例生成请求缺少requirement参数")
                return Response(
                    {'error': '请输入产品需求内容'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 处理文件名（使用用户需求和时间）
            # 1. 截取需求前20个字符作为标识（更长更具辨识度）
            truncated_req = requirement[:20].strip() if requirement else "default"

            # 2. 清理文件名中的特殊字符（替换为下划线）
            invalid_chars = r'[\\/*?:"<>| ]'  # 包含空格，统一替换
            cleaned_req = re.sub(invalid_chars, '_', truncated_req)

            # 3. 生成时间戳（使用下划线连接，不含空格）
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")  # 格式：20250726_153045

            # 4. 组合文件名并添加.mm扩展名
            outfile_name = f"{cleaned_req}_{current_time}.mm"

            # 如果用户未提供prompt，使用默认模板
            final_prompt = user_prompt if user_prompt else self.DEFAULT_PROMPT.format(requirement=requirement)

            # 2. 调用DeepSeek API生成测试用例
            try:
                deepseek = DeepSeekClient()
                raw_response = deepseek.generate_test_cases(requirement, final_prompt)
                if not raw_response:
                    raise ValueError("未从API获取到有效响应")
            except Exception as e:
                logger.error(f"DeepSeek API调用失败: {str(e)}", exc_info=True)
                return Response(
                    {'error': f'AI接口调用失败: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # 3. 解析API响应为结构化数据
            test_cases = self._parse_test_cases(raw_response)

            # 4. 确保输出目录存在
            output_dir = os.path.join(settings.MEDIA_ROOT, 'tool_outputs')
            os.makedirs(output_dir, exist_ok=True)

            # 5. 创建FreeMind格式文件
            with tempfile.NamedTemporaryFile(suffix='.mm', delete=False, mode='w', encoding='utf-8') as tmp:
                # 生成FreeMind XML内容
                mindmap_xml = self._generate_freemind(test_cases)
                tmp.write(mindmap_xml)
                tmp.flush()  # 确保内容写入磁盘

                # 6. 保存到模型（使用自定义文件名）
                log = ToolUsageLog.objects.create(
                    user=request.user,
                    tool_type='TEST_CASE',
                    input_data=json.dumps({
                        'requirement': requirement,
                        'prompt': final_prompt
                    })
                )

                # 使用Django的File类处理文件保存
                with open(tmp.name, 'rb') as f:
                    log.output_file.save(outfile_name, File(f), save=True)

                # 清理临时文件
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
                'raw_response': raw_response
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
        """解析API响应为层级结构"""
        sections = {}
        current_section = None
        current_case = []

        for line in raw_response.split('\n'):
            line = line.strip()
            # 处理标题行（# 开头）
            if line.startswith('#'):
                # 如果有未完成的用例，添加到当前章节
                if current_case and current_section:
                    sections[current_section].append('\n'.join(current_case))
                    current_case = []
                # 设置新章节
                current_section = line.lstrip('# ').strip()
                sections[current_section] = []
            # 处理列表项（- 或 * 开头）
            elif line.startswith(('-', '*')) and current_section:
                # 如果有未完成的用例，添加到当前章节
                if current_case:
                    sections[current_section].append('\n'.join(current_case))
                    current_case = []
                # 添加新用例的第一行
                current_case.append(line.lstrip('-* ').strip())
            # 处理用例的多行内容
            elif current_case and current_section:
                current_case.append(line)

        # 添加最后一个用例
        if current_case and current_section:
            sections[current_section].append('\n'.join(current_case))

        # 如果没有解析到任何章节，创建一个默认章节
        if not sections:
            sections["默认测试场景"] = [raw_response]

        return {
            "title": "AI生成测试用例",
            "structure": sections
        }

    def _generate_freemind(self, test_cases):
        """生成飞书兼容的FreeMind格式XML"""
        # 避免XML命名空间问题
        ET.register_namespace('', 'http://freemind.sourceforge.net/wiki/index.php/XML')

        # FreeMind根节点
        map_root = ET.Element("map")
        map_root.set("version", "1.0.1")

        # 根主题（对应测试用例标题）
        root_topic = ET.SubElement(map_root, "node")
        root_topic.set("TEXT", test_cases["title"])
        root_topic.set("STYLE", "bubble")
        root_topic.set("COLOR", "#000000")  # 黑色根节点

        # 构建层级结构：场景（一级节点）-> 测试用例（二级节点）
        for scene, cases in test_cases["structure"].items():
            if not scene or not cases:  # 跳过空场景或空用例
                continue

            # 场景节点
            scene_node = ET.SubElement(root_topic, "node")
            scene_node.set("TEXT", scene)
            scene_node.set("COLOR", "#FF7F50")  # 珊瑚色场景节点
            scene_node.set("STYLE", "fork")

            # 测试用例节点
            for case in cases:
                if case:  # 跳过空用例
                    case_node = ET.SubElement(scene_node, "node")
                    case_node.set("TEXT", case)
                    case_node.set("COLOR", "#4682B4")  # 钢蓝色用例节点
                    case_node.set("STYLE", "bullet")

        # 格式化XML
        rough_string = ET.tostring(map_root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        # 移除XML声明，避免飞书解析问题
        return '\n'.join([line for line in reparsed.toprettyxml(indent="  ").split('\n') if line.strip()])