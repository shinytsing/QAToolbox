from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import ToolUsageLog
from .utils import DeepSeekClient
import tempfile
import os
import json
import shutil
from django.conf import settings
# 使用 xmind 库的核心类
from xmind.core.markerref import MarkerId
from xmind.core.topic import TopicElement
from xmind.core.workbook import WorkbookDocument


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

            # 3. 创建XMind文件（使用xmind库底层API）
            with tempfile.NamedTemporaryFile(suffix='.xmind', delete=False) as tmp:
                # 初始化工作簿
                workbook = WorkbookDocument()
                sheet = workbook.createSheet()
                root_topic = sheet.getRootTopic()
                root_topic.setTitle(test_cases["title"])

                # 递归添加主题
                self._add_topics(root_topic, test_cases["structure"])

                # 保存到临时文件
                workbook.save(tmp.name)

                # 4. 准备目标路径
                media_dir = os.path.join(settings.MEDIA_ROOT, 'tool_outputs')
                os.makedirs(media_dir, exist_ok=True)
                target_path = os.path.join(media_dir, os.path.basename(tmp.name))

                # 5. 保存日志记录
                log = ToolUsageLog.objects.create(
                    user=request.user,
                    tool_type='TEST_CASE',
                    input_data=json.dumps({
                        'requirement': requirement,
                        'prompt': user_prompt
                    }),
                    output_file=os.path.join('tool_outputs', os.path.basename(tmp.name))
                )

                # 6. 移动文件
                shutil.move(tmp.name, target_path)

                return Response({
                    'download_url': f'/tools/download/{os.path.basename(target_path)}',
                    'log_id': log.id,
                    'raw_response': raw_response
                })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _parse_test_cases(self, raw_response):
        """解析API响应为多级结构（保持不变）"""
        structure = {}
        current_section = None  # 一级标题（## 开头）
        current_subsection = None  # 二级标题（### 开头）

        for line in raw_response.split('\n'):
            line = line.strip()
            if not line:
                continue

            if line.startswith('## '):
                current_section = line[3:].strip()
                structure[current_section] = []
                current_subsection = None
            elif line.startswith('### '):
                if current_section:
                    current_subsection = line[4:].strip()
                    structure[current_section].append({"name": current_subsection, "items": []})
            elif line.startswith('- '):
                case = line[2:].strip()
                if current_subsection and current_section:
                    for item in structure[current_section]:
                        if item["name"] == current_subsection:
                            item["items"].append(case)
                            break
                elif current_section:
                    structure[current_section].append(case)

        return {"title": "AI Generated Test Cases", "structure": structure}

    def _add_topics(self, parent_topic, structure_data):
        """递归添加主题到XMind（适配xmind库API）"""
        if isinstance(structure_data, dict):
            # 处理一级结构（字典：section -> items）
            for section, items in structure_data.items():
                section_topic = parent_topic.addSubTopic()
                section_topic.setTitle(section)
                # 给一级标题添加标记（可选）
                section_topic.addMarker(MarkerId.TASK_START)
                self._add_topics(section_topic, items)
        elif isinstance(structure_data, list):
            # 处理二级/三级结构（列表）
            for item in structure_data:
                if isinstance(item, dict) and "name" in item and "items" in item:
                    # 二级标题
                    sub_topic = parent_topic.addSubTopic()
                    sub_topic.setTitle(item["name"])
                    sub_topic.addMarker(MarkerId.TASK_PLAN)
                    self._add_topics(sub_topic, item["items"])
                else:
                    # 测试用例条目
                    case_topic = parent_topic.addSubTopic()
                    case_topic.setTitle(str(item))
                    case_topic.addMarker(MarkerId.NOTE)