import streamlit as st
import requests
import pandas as pd
import json
import re
import time
import zipfile
import io

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="MysteryNarrator - 强制锁脸版", page_icon="🔒", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d; color: #c0c0c0; }
    [data-testid="stSidebar"] { background-color: #141414; border-right: 1px solid #222; }
    .stButton > button { background-color: #d32f2f; color: white; border: none; width: 100%; font-weight: bold; }
    .stButton > button:hover { background-color: #b71c1c; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心功能函数
# ==========================================
def get_headers(api_key): return {"Authorization": f"Bearer {api_key}"}
def clean_json_text(text): return re.sub(r'<think>.*?</think>', '', re.sub(r'```json|```', '', text), flags=re.DOTALL).strip()

# ASR 听写
def transcribe_audio(audio_file, api_key):
    url = "https://api.siliconflow.cn/v1/audio/transcriptions"
    files = {'file': (audio_file.name, audio_file.getvalue(), audio_file.type), 'model': (None, 'FunAudioLLM/SenseVoiceSmall'), 'response_format': (None, 'verbose_json')}
    try: return requests.post(url, headers=get_headers(api_key), files=files, timeout=120).json()
    except: return None

# 角色提取
def extract_characters_silicon(script_text, model, key):
    url = "https://api.siliconflow.cn/v1/chat/completions"
    sys_prompt = "提取文案中的【剧情角色】(不含博主)。输出JSON列表: [{'name':'xx','prompt':'...'}]"
    try:
        res = requests.post(url, json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":script_text}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        return pd.DataFrame(json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))) if res.status_code == 200 else None
    except: return None

# 【核心升级】分镜分析 (只留占位符)
def analyze_segments(segments, char_names, style, res_p, model, key):
    input_json = json.dumps(segments, ensure_ascii=False)
    # 只告诉 AI 有哪些角色名，不给详细描述，防止它偷懒只写名字
    char_list_str = ", ".join(char_names)
    
    sys_prompt = f"""
    你是悬疑片导演。为【已分段解说词 JSON】设计画面。
    可用角色名: {char_list_str}
    风格:{style}, 构图:{res_p}
    任务:
    1. 判断类型: "CHARACTER" 或 "SCENE"。
    2. 编写英文Prompt(final_prompt): 
       - **关键规则**: 如果镜头出现角色，**只需写角色名占位符，如 [博主(我)] 或 [Liam]**，不要写具体外貌。
       - 必须包含动作、情绪和风格词。
    输出: 纯 JSON 列表，包含 "index", "script", "type", "final_prompt"。
    """
    try:
        res = requests.post("https://api.siliconflow.cn/v1/chat/completions", json={"model": model, "messages": [{"role":"system","content":sys_prompt}, {"role":"user","content":input_json}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=120)
        if res.status_code == 200:
            result_list = json.loads(clean_json_text(res.json()['choices'][0]['message']['content']))
            if isinstance(result_list, dict): result_list = result_list.get('segments', [])
            merged = []
            for i, seg in enumerate(segments):
                visual = next((item for item in result_list if item.get('index') == i), None)
                merged.append({"start": seg['start'], "end": seg['end'], "script": seg['text'], "type": visual['type'] if visual else "SCENE", "final_prompt": visual['final_prompt'] if visual else f"Suspense scene, {style}"})
            return pd.DataFrame(merged)
        return None
    except: return None

# 【新增】强制注入角色描述
def inject_character_prompts(shot_df, char_df):
    if shot_df is None or char_df is None: return shot_df
    
    # 把角色表转成字典: {"[博主(我)]": "A 30-year-old...", "[Liam]": "..."}
    char_dict = {f"[{row['name']}]": row['prompt'] for _, row in char_df.iterrows()}
    
    def replace_placeholder(prompt):
        # 查找所有 [...] 占位符
        placeholders = re.findall(r'\[.*?\]', prompt)
        for ph in placeholders:
            # 如果在字典里，就替换成完整描述，并加权重
            if ph in char_dict:
                full_desc = char_dict[ph]
                # 使用括号和 :1.2 增加权重，确保画师重视
                prompt = prompt.replace(ph, f"({full_desc}:1.2)")
        return prompt

    # 对每一行的 final_prompt 进行替换
    shot_df['final_prompt'] = shot_df['final_prompt'].apply(replace_placeholder)
    return shot_df

# 画图
def generate_image(prompt, size, key):
    try:
        res = requests.post("https://api.siliconflow.cn/v1/images/generations", json={"model": "Kwai-Kolors/Kolors", "prompt": prompt, "image_size": size, "batch_size": 1}, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
        return res.json()['data'][0]['url'] if res.status_code == 200 else "Error"
    except: return "Error"

# SRT & ZIP
def create_srt(df):
    def fmt(s): ms=int((s-int(s))*1000); m,s=divmod(int(s),60); h,m=divmod(m,60); return f"{h:02}:{m:02}:{s:02},{ms:03}"
    return "".join([f"{i+1}\n{fmt(r['start'])} --> {fmt(r['end'])}\n{r['script']}\n\n" for i,r in df.iterrows()])

# ==========================================
# 3. 界面逻辑
# ==========================================
if 'char_df' not in st.session_state: st.session_state.char_df = None
if 'shot_df' not in st.session_state: st.session_state.shot_df = None
if 'gen_imgs' not in st.session_state: st.session_state.gen_imgs = {}
if 'segments' not in st.session_state: st.session_state.segments = None

with st.sidebar:
    st.markdown("### 🔑 API"); api_key = st.text_input("Key", type="password")
    st.markdown("### 🕵️ 博主形象 (重要!)")
    # 增加了权重提示
    fixed_host = st.text_area("Prompt", "(A 30-year-old Asian man, green cap, leather jacket, stubble beard, looking at camera:1.3)", height=80, help="用括号和:1.x增加权重")
    st.markdown("### 🛠️ 设置"); model = st.selectbox("大脑", ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"])
    res_str, res_prompt = {"16:9":("1280x720","Cinematic 16:9"), "9:16":("720x1280","9:16 portrait")}[st.selectbox("画幅", ["16:9", "9:16"])]
    style = st.text_area("风格", "Film noir, suspense thriller, low key lighting, high contrast.", height=60)

st.title("🔒 MysteryNarrator V8 (强制锁脸)")

# 1. 上传音频 & 听写
audio = st.file_uploader("1. 上传录音 (MP3/WAV)", type=['mp3','wav','m4a'])
if audio and api_key and st.button("👂 2. 听写并提取角色"):
    with st.spinner("听写中..."):
        asr = transcribe_audio(audio, api_key)
        if asr:
            st.session_state.segments = [{"index":i,"start":s['start'],"end":s['end'],"text":s['text']} for i,s in enumerate(asr.get('segments',[]))]
            full_text = "".join([s['text']+" " for s in st.session_state.segments])
            with st.spinner("分析角色..."):
                df = extract_characters_silicon(full_text, model, api_key)
                if df is not None:
                    host = pd.DataFrame([{"name":"博主(我)", "prompt":fixed_host}])
                    st.session_state.char_df = pd.concat([host, df], ignore_index=True)
                    st.success("完成!")

if st.session_state.char_df is not None:
    st.session_state.char_df = st.data_editor(st.session_state.char_df, num_rows="dynamic", key="c_ed")

# 2. 生成分镜 & 注入角色
if st.button("🎬 3. 生成分镜 (强制注入)", disabled=st.session_state.segments is None or st.session_state.char_df is None):
    with st.spinner("设计分镜并注入角色描述..."):
        # a. AI 生成带占位符的分镜
        char_names = st.session_state.char_df['name'].tolist()
        df = analyze_segments(st.session_state.segments, char_names, style, res_prompt, model, api_key)
        if df is not None:
            # b. 【关键步骤】代码强制替换占位符为完整描述
            df = inject_character_prompts(df, st.session_state.char_df)
            st.session_state.shot_df = df
            st.success("分镜完成，角色已强制锁定！")

if st.session_state.shot_df is not None:
    st.session_state.shot_df = st.data_editor(st.session_state.shot_df, column_config={"start":st.column_config.NumberColumn(format="%.2f"),"end":st.column_config.NumberColumn(format="%.2f")}, num_rows="dynamic", key="s_ed")
    
    # 3. 画图 & 下载
    st.markdown("---")
    c1, c2 = st.columns(2)
    if c1.button("🚀 4. 开始绘图"):
        bar = st.progress(0); log = st.empty(); tot = len(st.session_state.shot_df)
        for i, r in st.session_state.shot_df.iterrows():
            log.text(f"绘制 {i+1}/{tot}"); url = generate_image(r['final_prompt'], res_str, api_key)
            if "Error" not in url: st.session_state.gen_imgs[i] = url
            bar.progress((i+1)/tot); 
            if i<tot-1: time.sleep(32)
        st.success("完成!")
        
    if c2.button("📦 5. 下载剪映包"):
        if not st.session_state.gen_imgs: st.warning("先画图!")
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("subtitle.srt", create_srt(st.session_state.shot_df))
                for i,u in st.session_state.gen_imgs.items():
                    try: zf.writestr(f"{i+1:03d}.jpg", requests.get(u).content)
                    except: pass
            st.download_button("⬇️ ZIP", buf.getvalue(), "mystery_project.zip", "application/zip")
