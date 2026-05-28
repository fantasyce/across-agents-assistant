from __future__ import annotations

EXIT_WORDS = ["拜拜", "退出", "停止", "结束", "晚安", "byebye", "bye", "再见"]


def normalize_cn(text: str) -> str:
    text = text.replace(" ", "").replace("　", "").replace(",", "").replace("，", "")

    # 繁简转换及常见同音字纠错 (luo, lu, nuo, ruo)
    for char in ["洛", "罗", "路", "炉", "爐", "诺", "若", "裸", "萝", "络", "骆", "落"]:
        text = text.replace(char, "落")

    # 把常见的发音错误的 "xiao" 替换为 "小"
    text = text.replace("下落", "小落")

    return text


def is_hallucination(text: str) -> bool:
    if not text:
        return True
    # Remove punctuation
    cleaned = text.replace(" ", "").replace("　", "").replace("，", "").replace(",", "").replace("。", "").replace(".", "").replace("？", "").replace("?", "").strip()
    if not cleaned:
        return True

    # Common whisper hallucinations (video subtitle artifacts)
    hallucinations = [
        "字幕", "Amara", "amara", "点赞", "订阅", "转发", "打赏", "明镜", "点点节目", "谢谢观看", "请不吝", "支持明镜", "支持点点",
        "观看", "播放", "频道", "优酷", "youtube", "B站", "bilibili", "视频", "欢迎收看", "未经允许", "严禁"
    ]

    for h in hallucinations:
        if h in text:
            return True

    # Filter very short noise-like utterances (single character noises)
    # Only filter extremely short meaningless sounds, not valid greetings like "你好"
    if len(cleaned) <= 2:
        noise_words = ["嗯", "啊", "哦", "呃", "哈", "嘿", "喂"]
        if cleaned in noise_words:
            return True

    return False

def contains_wake_word(text: str, wake_word: str = "小落") -> bool:
    if not text:
        return False

    # Common mis-transcriptions
    for hallucination in [wake_word, "小洛", "还好", "还号", "夏洛", "小弱", "下落", "小炉", "小骆", "小诺", "小若", "小裸", "小路", "小陆"]:
        if hallucination in text.replace(" ", ""):
            return True
    return False

def strip_wake_word(text: str, wake_word: str = "小落") -> str:
    if not text:
        return ""
    actual = text.replace(" ", "").replace("　", "")
    for variant in [
        wake_word * 2, wake_word,
        "小洛小洛", "小洛", "还好你好", "还好", "夏洛", "小弱", "下落", "小炉", "小诺", "小骆", "小若", "小裸", "小陆", "小路",
        "你在吗", "在吗", "?", "？", ",", "，", ".", "。"
    ]:
        actual = actual.replace(variant, "")
    return actual.strip()


def is_exit_word(text: str) -> bool:
    if not text:
        return False
    normalized = normalize_cn(text)

    # 明确的指令式退出
    if "再见小落" in normalized or "小落再见" in normalized or "退下" in normalized or "再见小洛" in normalized or "小洛再见" in normalized:
        return True

    # 如果用户的话非常简短（比如只有"再见"两个字），也认为是退出
    # 防止把包含"再见"的正常句子（比如"我要去见个朋友再见"）误判为退出
    if len(normalized) <= 4 and any(exit_word in normalized for exit_word in EXIT_WORDS):
        return True

    return False
