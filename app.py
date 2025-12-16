import streamlit as st
import requests
import pandas as pd
import json
import re
import time

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - 悬疑解说助手 (锁脸版)",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 悬疑黑红配色 CSS
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    h1, h2, h3 { color: #d32f2f !important; font-family: sans-serif; font-weight: 700; }
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-testid="stSelectboxInner"] {
        background-color: #1e1e1e !important; color: #e0e0e0 !important; border: 1px solid #333 !important;
    }
    .stButton > button {
        background-color: #d32f2f; color: white; border: none; width: 100%; padding: 10px; font-weight: bold;
    }
    .stButton > button:hover { background-color: #b71c1c; }
    [data-testid="stDataFrame"] { border: 1px solid #333; }
    .stSuccess { background-color: #1b5e20 !important; color: #fff !important; }
    .stInfo { background-color: #0d47a1 !important; color: #fff !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数
# ==========================================

def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def clean_json_text(text):
    text = re.sub(r'```json', '', text)
    text = re.sub(r'```', '', text)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()

# --- 功能 A: 角色分析 (只找剧情人物) ---
def extract_characters_silicon(script_text, model_choice, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 【修改点】: 明确告诉 AI 不要找博主，只找剧情里的人
    system_prompt = """
    你是一位悬疑片选角导演。请阅读文案，提取文案中出现的【剧情角色】（如受害者、嫌疑人、目击者）。
    
    【重要规则】
    1. **不要**提取 "博主"、"解说员" 或 "我"。
    2. 为每个提取的角色生成英文外貌 Prompt (30词以内)。
    3. 输出纯 JSON 对象列表: [{"name": "受害者李某", "prompt": "A young woman..."}, {"name": "嫌疑人张三", "prompt": "..."}]
    """

    payload = {
        "model": model_choice,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return pd.DataFrame(json.loads(clean_json_text(content)))
        else:
            st.error(f"角色分析失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 B: 智能分镜分析 ---
def analyze_script_with_characters(script_text, character_data, style_desc, resolution_prompt, model_choice, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 将角色数据转化为字符串提示
    char_prompt_list = ""
    for _, row in character_data.iterrows():
        char_prompt_list += f"- [{row['name']}]: {row['prompt']}\n"

    system_prompt = f"""
    你是一位悬疑电影导演。根据文案和角色表设计分镜。
    
    【角色表 (必须严格引用)】
    {char_prompt_list}
    
    【风格与构图】
    - 风格: {style_desc}
    - 构图: {resolution_prompt} (优先使用远景 Long shot)
    
    【任务】
    1. 拆分为 3-6 秒的镜头。
    2. 类型(type): "CHARACTER"(有人) 或 "SCENE"(空镜)。
    3. 英文 Prompt (final_prompt): 
       - 必须包含构图词(Long shot等)。
       - **关键**: 如果镜头涉及角色表中的人物，必须直接复制角色表中的英文描述。
       - SCENE 镜头严禁出现人。

    【输出】纯 JSON 对象列表: "time", "script", "type", "visual_desc", "final_prompt"。
    """

    payload = {
        "model": model_choice,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=120)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return pd.DataFrame(json.loads(clean_json_text(content)))
        else:
            st.error(f"分镜生成失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 C: 图片生成 ---
def generate_image_kolors(prompt, resolution_str, api_key):
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    payload = {
        "model": "Kwai-Kolors/Kolors",
        "prompt": prompt,
        "image_size": resolution_str,
        "batch_size": 1
    }
    
    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=60)
        if response.status_code == 200:
            return response.json().get('data', [{}])[0].get('url')
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================================
# 3. 界面逻辑
# ==========================================

# 初始化
if 'character_df' not in st.session_state: st.session_state.character_df = None
if 'shot_list_df' not in st.session_state: st.session_state.shot_list_df = None

with st.sidebar:
    st.markdown("### 🔑 API 设置")
    api_key = st.text_input("SiliconFlow Key", type="password")
    
    st.markdown("---")
    st.markdown("### 🕵️ 固定博主形象")
    # 这里是你锁定的形象，不会变
    fixed_host_prompt = st.text_area("博主 Prompt", value="A 30-year-old Asian man, wearing a green cap and brown leather jacket, stubble beard, looking at the viewer, dramatic lighting.", height=100)
    
    st.markdown("---")
    st.markdown("### 🧠 模型选择")
    model_choice = st.selectbox(
        "选择大脑",
        ("Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1-Distill-Llama-70B"),
        index=0
    )
    
    st.markdown("---")
    st.markdown("### 📐 画面设置")
    resolution_option = st.selectbox("画幅", ("电影宽屏 (16:9)", "竖屏 (9:16)"), index=0)
    res_map = {"电影宽屏 (16:9)": ("1280x720", "Cinematic 16:9"), "竖屏 (9:16)": ("720x1280", "9:16 portrait")}
    resolution_str, resolution_prompt = res_map[resolution_option]

    default_style = "Film noir, suspense thriller, low key lighting, high contrast, gritty film grain."
    visual_style = st.text_area("影调风格", value=default_style, height=80)

st.title("🕵️‍♂️ MysteryNarrator V5.1 (锁脸修正版)")

# Step 1
st.markdown("### 📝 1. 输入文案")
script_input = st.text_area("解说词...", height=150)

# Step 2
st.markdown("---")
st.markdown("### 👥 2. 角色定妆")
if st.button("🔍 提取角色 (自动注入博主)"):
    if not api_key: st.warning("请填 Key")
    elif not script_input: st.warning("请填文案")
    else:
        with st.spinner("正在提取剧情人物，并注入博主形象..."):
            # 1. AI 找剧情人物 (Liam, Sylvia 等)
            story_chars_df = extract_characters_silicon(script_input, model_choice, api_key)
            
            if story_chars_df is not None:
                # 2. 【核心修改】强制创建一个博主行
                host_row = pd.DataFrame([{"name": "博主 (我)", "prompt": fixed_host_prompt}])
                
                # 3. 把博主拼到第一行
                final_df = pd.concat([host_row, story_chars_df], ignore_index=True)
                
                st.session_state.character_df = final_df
                st.success("✅ 角色提取成功！博主已锁定为侧边栏设定。")

if st.session_state.character_df is not None:
    edited_char_df = st.data_editor(st.session_state.character_df, num_rows="dynamic", key="char_edit")
    st.session_state.character_df = edited_char_df

# Step 3
st.markdown("---")
st.markdown("### 🎬 3. 生成分镜")
btn_disabled = st.session_state.character_df is None
if st.button("🧠 生成分镜表", disabled=btn_disabled):
    with st.spinner("导演正在设计镜头..."):
        shot_df = analyze_script_with_characters(
            script_input, st.session_state.character_df, visual_style, resolution_prompt, model_choice, api_key
        )
        if shot_df is not None:
            st.session_state.shot_list_df = shot_df
            st.success("分镜生成成功！")

if st.session_state.shot_list_df is not None:
    edited_shot_df = st.data_editor(st.session_state.shot_list_df, num_rows="dynamic", key="shot_edit")
    st.session_state.shot_list_df = edited_shot_df

    # Step 4
    st.markdown("---")
    st.markdown("### 🖼️ 4. 开始拍摄")
    if st.button("🚀 启动自动绘图"):
        log = st.container()
        cols = st.columns(3)
        total = len(edited_shot_df)
        bar = st.progress(0)
        
        for i, row in edited_shot_df.iterrows():
            with log: st.caption(f"正在绘制 [{i+1}/{total}]: {row['script'][:10]}...")
            url = generate_image_kolors(row['final_prompt'], resolution_str, api_key)
            
            if "Error" in url: st.error(f"失败: {url}")
            else:
                with cols[i%3]: st.image(url, caption=f"Shot {i+1}")
            
            bar.progress((i+1)/total)
            if i < total-1: time.sleep(32)
        st.success("杀青！")
