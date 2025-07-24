def _parse_test_cases(self, raw_response):
    """解析API响应为XMind所需的结构化数据（支持多级用例）"""
    structure = {}
    current_section = None
    current_subsection = None

    for line in raw_response.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 一级标题（## 开头）
        if line.startswith('## '):
            current_section = line[3:].strip()
            structure[current_section] = []
            current_subsection = None
        # 二级标题（### 开头）
        elif line.startswith('### '):
            if current_section:
                current_subsection = line[4:].strip()
                structure[current_section].append({
                    "name": current_subsection,
                    "items": []
                })
        # 测试用例（- 开头）
        elif line.startswith('- '):
            case = line[2:].strip()
            if current_subsection and current_section:
                # 找到当前子节点并添加用例
                for item in structure[current_section]:
                    if item["name"] == current_subsection:
                        item["items"].append(case)
                        break
            elif current_section:
                # 直接添加到一级节点
                structure[current_section].append(case)

    return {
        "title": "AI Generated Test Cases",
        "structure": structure
    }

