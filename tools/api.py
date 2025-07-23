from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import ToolUsageLog
from .serializers import ToolUsageLogSerializer
import tempfile
from xmindwriter import XMindWriter


class GenerateTestCasesAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        requirement = request.data.get('requirement')

        # 1. 生成测试用例逻辑
        test_cases = self._generate_test_cases(requirement)

        # 2. 创建XMind文件
        with tempfile.NamedTemporaryFile(suffix='.xmind', delete=False) as tmp:
            xmind = XMindWriter()
            xmind.create_from_structure(test_cases)
            xmind.save(tmp.name)

            # 3. 保存到模型
            log = ToolUsageLog.objects.create(
                user=request.user,
                tool_type='TEST_CASE',
                input_data=requirement,
                output_file=tmp.name
            )

            return Response({
                'download_url': f'/tool/download/{os.path.basename(log.output_file.name)}',
                'log_id': log.id
            })

    def _generate_test_cases(self, requirement):
        """模拟测试用例生成逻辑"""
        return {
            "title": "Generated Test Cases",
            "structure": {
                "核心功能": ["正向用例1", "正向用例2"],
                "边界情况": ["异常输入", "极端条件"]
            }
        }