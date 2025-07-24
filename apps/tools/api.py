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
# 新增：用于生成FreeMind XML
import xml.etree.ElementTree as ET
from xml.dom import minidom
from django.conf import settings


class GenerateTestCasesAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        requirement = request.data.get('requirement')
        user_prompt = request.data.get('prompt')

        if not requirement or not user_prompt:
            return Response(
                {'error': 'requirement and prompt are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. 调用DeepSeek API生成测试用例
            deepseek = DeepSeekClient()
            raw_response = deepseek.generate_test_cases(requirement, user_prompt)

            # 2. 解析API响应为结构化数据
            test_cases = self._parse_test_cases(raw_response)

            # 3. 创建FreeMind格式文件（飞书兼容）
            with tempfile.NamedTemporaryFile(suffix='.mm', delete=False) as tmp:
                # 生成FreeMind XML内容
                mindmap_xml = self._generate_freemind(test_cases)
                tmp.write(mindmap_xml.encode('utf-8'))

                # 4. 保存到模型
                log = ToolUsageLog.objects.create(
                    user=request.user,
                    tool_type='TEST_CASE',
                    input_data=json.dumps({
                        'requirement': requirement,
                        'prompt': user_prompt
                    }),
                    output_file=os.path.join(settings.MEDIA_ROOT, 'tool_outputs', os.path.basename(tmp.name))
                )

                # 移动临时文件到媒体目录
                os.rename(tmp.name, log.output_file.path)

                return Response({
                    'download_url': f'/tool/download/{os.path.basename(log.output_file.name)}',
                    'log_id': log.id,
                    'raw_response': raw_response
                })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _parse_test_cases(self, raw_response):
        """解析API响应为层级结构（保持原逻辑不变）"""
        sections = {}
        current_section = None

        for line in raw_response.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                current_section = line.lstrip('# ').strip()
                sections[current_section] = []
            elif line.startswith('-') and current_section:
                sections[current_section].append(line.lstrip('- ').strip())

        return {
            "title": "AI生成测试用例",  # 根节点标题
            "structure": sections
        }

    def _generate_freemind(self, test_cases):
        """生成飞书兼容的FreeMind格式XML"""
        # FreeMind根节点
        map_root = ET.Element("map")
        map_root.set("version", "1.0.1")

        # 根主题（对应测试用例标题）
        root_topic = ET.SubElement(map_root, "node")
        root_topic.set("TEXT", test_cases["title"])
        root_topic.set("STYLE", "bubble")  # 飞书兼容的样式

        # 构建层级结构：场景（一级节点）-> 测试用例（二级节点）
        for scene, cases in test_cases["structure"].items():
            # 场景节点
            scene_node = ET.SubElement(root_topic, "node")
            scene_node.set("TEXT", scene)
            scene_node.set("COLOR", "#FFA500")  # 橙色标识场景

            # 测试用例节点
            for case in cases:
                case_node = ET.SubElement(scene_node, "node")
                case_node.set("TEXT", case)
                case_node.set("COLOR", "#0000FF")  # 蓝色标识用例

        # 格式化XML（增加缩进，飞书更易解析）
        rough_string = ET.tostring(map_root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")