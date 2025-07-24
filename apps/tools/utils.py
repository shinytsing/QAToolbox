import os
import requests
from django.conf import settings

import json
import xmind
# 从环境变量获取API密钥和速率限制
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
API_RATE_LIMIT = os.getenv('API_RATE_LIMIT', '10/minute')
RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD = API_RATE_LIMIT.split('/')
RATE_LIMIT_PERIOD = {'minute': 60, 'hour': 3600}[RATE_LIMIT_PERIOD]


class DeepSeekClient:
    API_BASE_URL = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set in environment variables")


    def generate_test_cases(self, requirement, user_prompt):
        """
        调用DeepSeek API生成测试用例
        :param requirement: 产品需求
        :param user_prompt: 用户自定义的提示词模板
        :return: 生成的测试用例结构
        """
        # 构建完整提示词
        full_prompt = user_prompt.format(requirement=requirement)

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一位专业的测试工程师，擅长生成全面的测试用例"},
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2048
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            response = requests.post(
                self.API_BASE_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")



# 可以在utils.py中补充XMind生成工具类
class XMindWriter:
    def create_from_structure(self, data):
        """从结构化数据创建XMind内容"""
        self.workbook = xmind.loads()  # 假设使用xmind库
        self.sheet = self.workbook.getPrimarySheet()
        self.sheet.setTitle(data["title"])

        root_topic = self.sheet.getRootTopic()

        for section, content in data["structure"].items():
            section_topic = root_topic.addSubTopic()
            section_topic.setTitle(section)

            for item in content:
                if isinstance(item, dict):
                    # 处理二级标题
                    sub_topic = section_topic.addSubTopic()
                    sub_topic.setTitle(item["name"])
                    # 添加用例
                    for case in item["items"]:
                        case_topic = sub_topic.addSubTopic()
                        case_topic.setTitle(case)
                else:
                    # 处理一级用例
                    case_topic = section_topic.addSubTopic()
                    case_topic.setTitle(item)

    def save(self, file_path):
        """保存到文件"""
        xmind.save(self.workbook, file_path)