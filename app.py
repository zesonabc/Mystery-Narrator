import streamlit as st
import requests
import pandas as pd
import json
import re
import time

# ==========================================
# 1. 页面配置与悬疑风格 CSS
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - 悬疑解说助手 (多角色版)",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 保持深色悬疑风格
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    h1, h2, h3 { color: #d32f2f !important; font-weight: 700; letter-spacing: 1px; }
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-testid="stSelectboxInner"] {
        background-color: #1e1e1e !important; color: #e0e0e0 !important; border: 1px solid #333 !important;
    }
    .stButton > button {
        background-color: #d32f2f; color: white; border: none; width: 100%; padding: 10px;
        font-weight: bold; text-transform: uppercase; letter-spacing: 1px; transition: all 0.3s;
    }
    .stButton > button:hover { background-color: #b71c1c; box-shadow: 0 4px 8px rgba(211,47,47,0.3); }
    [data-testid="stDataFrame"] { border: 1px solid #333; }
    hr { border-color: #222; }
    .stAlert { background-color: #1e1e1e !important; color: #e0e0e0 !important; border: 1px solid #333 !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数 (对接 SiliconFlow)
# ==========================================

def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def clean_json_text(text):
    text = re.sub(r'```json', '', text)
    text = re.sub(r'```', '', text)
    return text.strip()

# --- 功能 A: 角色分析 (新大脑 - Step 1) ---
def extract_characters_silicon(script_text, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    system_prompt = """
    你是一位专业的悬疑片选角导演。
    【任务】阅读解说文案，提取出所有出现的关键角色。
    【要求】
    1. 必须包含一个 "博主" (Host) 角色。
    2. 提取文案中提及的受害者、嫌疑人、警察等具体人物。
    3. 为每个角色生成一个简短、具体的英文外貌描述 Prompt (30词以内)。
    【输出格式】
    纯 JSON 对象列表，每个对象包含 "name" (角色名) 和 "prompt" (英文描述)。
    例如: [{"name": "博主", "prompt": "A man in 30s, serious face, wearing a trench coat..."}, {"name": "受害者李某", "prompt": "A young woman, long dark hair, pale face..."}]
    """

    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.5, # 降低随机性，让提取更准确
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

# --- 功能 B: 智能分镜分析 (新大脑 - Step 2) ---
def analyze_script_with_characters(script_text, character_data, style_desc, resolution_prompt, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 将角色数据转化为字符串提示
    char_prompt_list = ""
    for _, row in character_data.iterrows():
        char_prompt_list += f"- [{row['name']}]: {row['prompt']}\n"

    system_prompt = f"""
    你是一位悬疑电影导演，现在根据文案和已定角色进行分镜设计。
    
    【已定角色表 (必须严格引用)】
    {char_prompt_list}
    
    【全局风格约束】
    - 画风: {style_desc}
    - 构图: {resolution_prompt} (强制执行)
    - 景别: 优先使用远景(Long shot)、全景(Full shot)来交代环境和人物关系，慎用特写。
    
    【任务】
    1. 将文案按语速拆分为 3-6 秒的镜头。
    2. 判断镜头类型 (type): "CHARACTER" (有人物出现) 或 "SCENE" (纯空镜头/物证)。
    3. 编写英文 Prompt (final_prompt):
       - 格式: "[构图/景别], [画面主体描述], [环境/光影], [风格关键词]"
       - **关键**: 如果镜头涉及角色表中的人物，**必须**直接复制对应角色的英文 Prompt 插入描述中，确保形象统一。
       - SCENE 镜头不应出现任何人。

    【输出格式】
    纯 JSON 对象列表，包含: "time", "script", "type", "visual_desc", "final_prompt"。
    """

    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=90) # 分镜生成时间较长，增加超时
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return pd.DataFrame(json.loads(clean_json_text(content)))
        else:
            st.error(f"分镜分析失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 C: 图片生成 (画师) ---
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
# 3. 界面逻辑 (UI)
# ==========================================

# 初始化 session state
if 'character_df' not in st.session_state:
    st.session_state.character_df = None
if 'shot_list_df' not in st.session_state:
    st.session_state.shot_list_df = None

with st.sidebar:
    st.markdown("### ⚙️ API 设置")
    api_key = st.text_input("SiliconFlow Key (sk-...)", type="password", help="你的硅基流动密钥")
    
    st.markdown("---")
    st.markdown("### 🎬 导演风格设定")
    # 分辨率选择，对应不同的提示词和参数
    resolution_option = st.selectbox(
        "画幅比例",
        ("电影宽屏 (16:9)", "标准横屏 (4:3)", "竖屏短视频 (9:16)"),
        index=0
    )
    
    res_map = {
        "电影宽屏 (16:9)": ("1280x720", "Cinematic aspect ratio, wide screen, 16:9"),
        "标准横屏 (4:3)": ("1024x768", "4:3 aspect ratio"),
        "竖屏短视频 (9:16)": ("720x1280", "Vertical video, 9:16 aspect ratio, portrait mode")
    }
    resolution_str, resolution_prompt = res_map[resolution_option]

    # 专业的悬疑电影画风 Prompt
    st.markdown("### 🎨 悬疑影调 (Film Noir)")
    default_style = """Film noir aesthetic, suspense thriller atmosphere, low key lighting, high contrast shadows, cold color grading, gritty film grain, realistic cinematography, masterpiece, 8k resolution."""
    visual_style = st.text_area("风格提示词", value=default_style, height=120, help="定义整个视频的视觉基调")
    st.caption("💡 默认风格：暗调、高对比、冷色、颗粒感电影风。")

st.title("🕵️‍♂️ MysteryNarrator")
st.caption("多角色悬疑解说助手 | 硅基流动免费版")

# --- Step 1: 输入文案 ---
st.markdown("### 📝 Step 1: 输入解说文案")
script_input = st.text_area("在此粘贴你的完整解说词...", height=200, placeholder="例：大家好，我是老K。今天我们要讲的是发生在废弃公寓里的密室案件。受害者李某被发现时...")

# --- Step 2: 角色分析 ---
st.markdown("---")
st.markdown("### 👥 Step 2: 角色提取与定妆")
st.caption("AI 将自动分析文案中出现的所有人物，并为他们生成外貌描述。你可以在此确认和修改。")

if st.button("🔍 1. 分析文案角色"):
    if not api_key:
        st.warning("请先在侧边栏填入 API Key！")
    elif not script_input:
        st.warning("请先输入解说文案！")
    else:
        with st.spinner("🕵️‍♂️ 正在研读剧本，寻找登场人物..."):
            char_df = extract_characters_silicon(script_input, api_key)
            if char_df is not None:
                st.session_state.character_df = char_df
                st.success(f"成功提取 {len(char_df)} 个角色！请核对下表。")

# 角色编辑表格
if st.session_state.character_df is not None:
    edited_char_df = st.data_editor(
        st.session_state.character_df,
        column_config={
            "name": st.column_config.TextColumn("角色名 (中文)", width="small", required=True),
            "prompt": st.column_config.TextColumn("外貌描述 Prompt (英文, 可修改)", width="large", required=True),
        },
        use_container_width=True,
        num_rows="dynamic",
        key="char_editor"
    )
    st.session_state.character_df = edited_char_df
    st.info("👉 确认角色信息无误后，进行下一步分镜生成。")

# --- Step 3: 分镜生成 ---
st.markdown("---")
st.markdown("### 🎬 Step 3: 生成导演分镜表")
st.caption("AI 将根据文案、已定角色和风格，设计具体的镜头画面。")

generate_shot_disabled = st.session_state.character_df is None

if st.button("🧠 2. 生成分镜方案", disabled=generate_shot_disabled, help="请先完成角色分析"):
    with st.spinner("🎥 导演正在进行分镜设计，融合角色与场景..."):
        shot_df = analyze_script_with_characters(
            script_input, 
            st.session_state.character_df, 
            visual_style, 
            resolution_prompt, 
            api_key
        )
        if shot_df is not None:
            st.session_state.shot_list_df = shot_df
            st.success("分镜表生成完成！请在下方核对。")

# 分镜核对表格
if st.session_state.shot_list_df is not None:
    edited_shot_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "type": st.column_config.SelectboxColumn("类型", options=["CHARACTER", "SCENE"], width="small"),
            "final_prompt": st.column_config.TextColumn("最终绘图指令 (英文)", width="large"),
            "visual_desc": st.column_config.TextColumn("中文画面描述", width="medium"),
            "time": st.column_config.TextColumn("时长", width="small")
        },
        use_container_width=True,
        num_rows="dynamic",
        key="shot_editor"
    )
    st.session_state.shot_list_df = edited_shot_df

    # --- Step 4: 开始生产 ---
    st.markdown("---")
    st.markdown("### 🖼️ Step 4: 开始拍摄 (生产图片)")
    st.info(f"当前设置：**{resolution_option}** | 画风：悬疑电影感 | 速度限制：约 2 张/分钟")
    
    if st.button("🚀 启动自动绘图机 (真实生成)"):
        st.markdown("#### 📸 拍摄进度")
        log_container = st.container()
        gallery_cols = st.columns(3)
        
        total = len(edited_shot_df)
        progress_bar = st.progress(0)
        
        for index, row in edited_shot_df.iterrows():
            with log_container:
                st.caption(f"[{index+1}/{total}] 正在绘制镜头: {row['script'][:15]}... ({row['type']})")
            
            # 调用生图
            image_url = generate_image_kolors(row['final_prompt'], resolution_str, api_key)
            
            if "Error" in image_url:
                st.error(f"第 {index+1} 张失败: {image_url}")
            else:
                with gallery_cols[index % 3]:
                    st.image(image_url, caption=f"Shot {index+1}", use_column_width=True)
                    st.markdown(f"[下载原图]({image_url})")
            
            progress_bar.progress((index + 1) / total)
            
            # 强制冷却 (Kolors 免费版限制)
            if index < total - 1:
                with log_container:
                     st.write("⏳ 冷却中 (30s)...")
                time.sleep(32) 
        
        st.success("✅ 所有镜头拍摄完毕！杀青！")import streamlit as st
import requests
import pandas as pd
import json
import re
import time

# ==========================================
# 1. 页面配置与悬疑风格 CSS
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - 悬疑解说助手 (多角色版)",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 保持深色悬疑风格
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    h1, h2, h3 { color: #d32f2f !important; font-weight: 700; letter-spacing: 1px; }
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-testid="stSelectboxInner"] {
        background-color: #1e1e1e !important; color: #e0e0e0 !important; border: 1px solid #333 !important;
    }
    .stButton > button {
        background-color: #d32f2f; color: white; border: none; width: 100%; padding: 10px;
        font-weight: bold; text-transform: uppercase; letter-spacing: 1px; transition: all 0.3s;
    }
    .stButton > button:hover { background-color: #b71c1c; box-shadow: 0 4px 8px rgba(211,47,47,0.3); }
    [data-testid="stDataFrame"] { border: 1px solid #333; }
    hr { border-color: #222; }
    .stAlert { background-color: #1e1e1e !important; color: #e0e0e0 !important; border: 1px solid #333 !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数 (对接 SiliconFlow)
# ==========================================

def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def clean_json_text(text):
    text = re.sub(r'```json', '', text)
    text = re.sub(r'```', '', text)
    return text.strip()

# --- 功能 A: 角色分析 (新大脑 - Step 1) ---
def extract_characters_silicon(script_text, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    system_prompt = """
    你是一位专业的悬疑片选角导演。
    【任务】阅读解说文案，提取出所有出现的关键角色。
    【要求】
    1. 必须包含一个 "博主" (Host) 角色。
    2. 提取文案中提及的受害者、嫌疑人、警察等具体人物。
    3. 为每个角色生成一个简短、具体的英文外貌描述 Prompt (30词以内)。
    【输出格式】
    纯 JSON 对象列表，每个对象包含 "name" (角色名) 和 "prompt" (英文描述)。
    例如: [{"name": "博主", "prompt": "A man in 30s, serious face, wearing a trench coat..."}, {"name": "受害者李某", "prompt": "A young woman, long dark hair, pale face..."}]
    """

    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.5, # 降低随机性，让提取更准确
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

# --- 功能 B: 智能分镜分析 (新大脑 - Step 2) ---
def analyze_script_with_characters(script_text, character_data, style_desc, resolution_prompt, api_key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    
    # 将角色数据转化为字符串提示
    char_prompt_list = ""
    for _, row in character_data.iterrows():
        char_prompt_list += f"- [{row['name']}]: {row['prompt']}\n"

    system_prompt = f"""
    你是一位悬疑电影导演，现在根据文案和已定角色进行分镜设计。
    
    【已定角色表 (必须严格引用)】
    {char_prompt_list}
    
    【全局风格约束】
    - 画风: {style_desc}
    - 构图: {resolution_prompt} (强制执行)
    - 景别: 优先使用远景(Long shot)、全景(Full shot)来交代环境和人物关系，慎用特写。
    
    【任务】
    1. 将文案按语速拆分为 3-6 秒的镜头。
    2. 判断镜头类型 (type): "CHARACTER" (有人物出现) 或 "SCENE" (纯空镜头/物证)。
    3. 编写英文 Prompt (final_prompt):
       - 格式: "[构图/景别], [画面主体描述], [环境/光影], [风格关键词]"
       - **关键**: 如果镜头涉及角色表中的人物，**必须**直接复制对应角色的英文 Prompt 插入描述中，确保形象统一。
       - SCENE 镜头不应出现任何人。

    【输出格式】
    纯 JSON 对象列表，包含: "time", "script", "type", "visual_desc", "final_prompt"。
    """

    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=get_headers(api_key), timeout=90) # 分镜生成时间较长，增加超时
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return pd.DataFrame(json.loads(clean_json_text(content)))
        else:
            st.error(f"分镜分析失败: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {e}")
        return None

# --- 功能 C: 图片生成 (画师) ---
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
# 3. 界面逻辑 (UI)
# ==========================================

# 初始化 session state
if 'character_df' not in st.session_state:
    st.session_state.character_df = None
if 'shot_list_df' not in st.session_state:
    st.session_state.shot_list_df = None

with st.sidebar:
    st.markdown("### ⚙️ API 设置")
    api_key = st.text_input("SiliconFlow Key (sk-...)", type="password", help="你的硅基流动密钥")
    
    st.markdown("---")
    st.markdown("### 🎬 导演风格设定")
    # 分辨率选择，对应不同的提示词和参数
    resolution_option = st.selectbox(
        "画幅比例",
        ("电影宽屏 (16:9)", "标准横屏 (4:3)", "竖屏短视频 (9:16)"),
        index=0
    )
    
    res_map = {
        "电影宽屏 (16:9)": ("1280x720", "Cinematic aspect ratio, wide screen, 16:9"),
        "标准横屏 (4:3)": ("1024x768", "4:3 aspect ratio"),
        "竖屏短视频 (9:16)": ("720x1280", "Vertical video, 9:16 aspect ratio, portrait mode")
    }
    resolution_str, resolution_prompt = res_map[resolution_option]

    # 专业的悬疑电影画风 Prompt
    st.markdown("### 🎨 悬疑影调 (Film Noir)")
    default_style = """Film noir aesthetic, suspense thriller atmosphere, low key lighting, high contrast shadows, cold color grading, gritty film grain, realistic cinematography, masterpiece, 8k resolution."""
    visual_style = st.text_area("风格提示词", value=default_style, height=120, help="定义整个视频的视觉基调")
    st.caption("💡 默认风格：暗调、高对比、冷色、颗粒感电影风。")

st.title("🕵️‍♂️ MysteryNarrator")
st.caption("多角色悬疑解说助手 | 硅基流动免费版")

# --- Step 1: 输入文案 ---
st.markdown("### 📝 Step 1: 输入解说文案")
script_input = st.text_area("在此粘贴你的完整解说词...", height=200, placeholder="例：大家好，我是老K。今天我们要讲的是发生在废弃公寓里的密室案件。受害者李某被发现时...")

# --- Step 2: 角色分析 ---
st.markdown("---")
st.markdown("### 👥 Step 2: 角色提取与定妆")
st.caption("AI 将自动分析文案中出现的所有人物，并为他们生成外貌描述。你可以在此确认和修改。")

if st.button("🔍 1. 分析文案角色"):
    if not api_key:
        st.warning("请先在侧边栏填入 API Key！")
    elif not script_input:
        st.warning("请先输入解说文案！")
    else:
        with st.spinner("🕵️‍♂️ 正在研读剧本，寻找登场人物..."):
            char_df = extract_characters_silicon(script_input, api_key)
            if char_df is not None:
                st.session_state.character_df = char_df
                st.success(f"成功提取 {len(char_df)} 个角色！请核对下表。")

# 角色编辑表格
if st.session_state.character_df is not None:
    edited_char_df = st.data_editor(
        st.session_state.character_df,
        column_config={
            "name": st.column_config.TextColumn("角色名 (中文)", width="small", required=True),
            "prompt": st.column_config.TextColumn("外貌描述 Prompt (英文, 可修改)", width="large", required=True),
        },
        use_container_width=True,
        num_rows="dynamic",
        key="char_editor"
    )
    st.session_state.character_df = edited_char_df
    st.info("👉 确认角色信息无误后，进行下一步分镜生成。")

# --- Step 3: 分镜生成 ---
st.markdown("---")
st.markdown("### 🎬 Step 3: 生成导演分镜表")
st.caption("AI 将根据文案、已定角色和风格，设计具体的镜头画面。")

generate_shot_disabled = st.session_state.character_df is None

if st.button("🧠 2. 生成分镜方案", disabled=generate_shot_disabled, help="请先完成角色分析"):
    with st.spinner("🎥 导演正在进行分镜设计，融合角色与场景..."):
        shot_df = analyze_script_with_characters(
            script_input, 
            st.session_state.character_df, 
            visual_style, 
            resolution_prompt, 
            api_key
        )
        if shot_df is not None:
            st.session_state.shot_list_df = shot_df
            st.success("分镜表生成完成！请在下方核对。")

# 分镜核对表格
if st.session_state.shot_list_df is not None:
    edited_shot_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "type": st.column_config.SelectboxColumn("类型", options=["CHARACTER", "SCENE"], width="small"),
            "final_prompt": st.column_config.TextColumn("最终绘图指令 (英文)", width="large"),
            "visual_desc": st.column_config.TextColumn("中文画面描述", width="medium"),
            "time": st.column_config.TextColumn("时长", width="small")
        },
        use_container_width=True,
        num_rows="dynamic",
        key="shot_editor"
    )
    st.session_state.shot_list_df = edited_shot_df

    # --- Step 4: 开始生产 ---
    st.markdown("---")
    st.markdown("### 🖼️ Step 4: 开始拍摄 (生产图片)")
    st.info(f"当前设置：**{resolution_option}** | 画风：悬疑电影感 | 速度限制：约 2 张/分钟")
    
    if st.button("🚀 启动自动绘图机 (真实生成)"):
        st.markdown("#### 📸 拍摄进度")
        log_container = st.container()
        gallery_cols = st.columns(3)
        
        total = len(edited_shot_df)
        progress_bar = st.progress(0)
        
        for index, row in edited_shot_df.iterrows():
            with log_container:
                st.caption(f"[{index+1}/{total}] 正在绘制镜头: {row['script'][:15]}... ({row['type']})")
            
            # 调用生图
            image_url = generate_image_kolors(row['final_prompt'], resolution_str, api_key)
            
            if "Error" in image_url:
                st.error(f"第 {index+1} 张失败: {image_url}")
            else:
                with gallery_cols[index % 3]:
                    st.image(image_url, caption=f"Shot {index+1}", use_column_width=True)
                    st.markdown(f"[下载原图]({image_url})")
            
            progress_bar.progress((index + 1) / total)
            
            # 强制冷却 (Kolors 免费版限制)
            if index < total - 1:
                with log_container:
                     st.write("⏳ 冷却中 (30s)...")
                time.sleep(32) 
        
        st.success("✅ 所有镜头拍摄完毕！杀青！")
