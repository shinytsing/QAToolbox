from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import ToolUsageLog
from .serializers import ToolUsageLogSerializer
from .utils import DeepSeekClient
import tempfile
import os
from xmindwriter import XMindWriter
from django.conf import settings
import json


class GenerateTestCasesAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        requirement = request.data.get('requirement')
        user_prompt = request.data.get('prompt')  # 接收用户自定义提示词

        if not requirement or not user_prompt:
            return Response(
                {'error': 'requirement and prompt are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. 调用DeepSeek API生成测试用例
            deepseek = DeepSeekClient()
            raw_response = deepseek.generate_test_cases(requirement, user_prompt)

            # 2. 解析API响应为结构化数据（根据你的提示词格式调整）
            test_cases = self._parse_test_cases(raw_response)

            # 3. 创建XMind文件
            with tempfile.NamedTemporaryFile(suffix='.xmind', delete=False) as tmp:
                xmind = XMindWriter()
                xmind.create_from_structure(test_cases)
                xmind.save(tmp.name)

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
        """解析API响应为XMind所需的结构化数据"""
        # 根据你的提示词输出格式进行解析
        # 示例：假设API返回的是Markdown列表格式
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
            "title": "AI Generated Test Cases",
            "structure": sections
        }