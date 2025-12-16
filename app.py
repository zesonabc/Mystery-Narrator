import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator Final", layout="wide", page_icon="🍌")

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .stButton>button { background-color: #8A2BE2; color: white; border: none; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🍌 Engine Status")
    st.write(f"SDK Version: `{genai.__version__}`")
    api_key = st.text_input("Gemini API Key", type="password")

# ================= 核心逻辑 =================

def extract_json(text):
    """强力清洗器：从 AI 的胡言乱语中提取 JSON"""
    try:
        # 1. 尝试直接解析
        return json.loads(text)
    except:
        # 2. 如果失败，用正则找 [ ... ] 列表结构
        try:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
    return None

def analyze_script(script, key):
    genai.configure(api_key=key)
    target_model = 'gemini-2.5-flash'
    
    try:
        model = genai.GenerativeModel(
            target_model,
            # 关键修改：开启 JSON 模式，强制 AI 听话
            generation_config={"response_mime_type": "application/json"}
        )
        
        prompt = f"""
        You are a mystery video director.
        Script: {script}
        Task: Split script into scenes. Write an Image Prompt.
        Output Format: A JSON Array of Objects.
        Example: [{{"script": "...", "prompt": "..."}}]
        """
        
        response = model.generate_content(prompt)
        text = response.text
        
        # 使用强力清洗器
        data = extract_json(text)
        
        if not data:
            st.error("AI 返回内容无法解析，原始内容如下：")
            st.code(text) # 把原始回复打印出来看看到底是个啥
            return None
            
        return data

    except Exception as e:
        st.error(f"文本分析失败 ({target_model}): {e}")
        return None

def generate_image(prompt, key):
    genai.configure(api_key=key)
    # 你的环境能用的模型
    model_name = 'gemini-2.5-flash-image'
    
    try:
        model = genai.GenerativeModel(model_name)
        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9"
        )
        return result.images[0]._pil_image
    except Exception as e:
        # 备用方案
        try:
            fallback = 'imagen-4.0-fast-generate-001'
            model = genai.GenerativeModel(fallback)
            result = model.generate_images(prompt=prompt, number_of_images=1)
            return result.images[0]._pil_image
        except:
            return f"画图失败: {e}"

# ================= 主界面 =================
st.title("🍌 MysteryNarrator (JSON Fix)")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 生成"):
    if not api_key:
        st.error("请填入 Key")
    else:
        # 检查版本
        if genai.__version__ < "0.8.3":
            st.error("请先更新 requirements.txt 并重启 App！")
            st.stop()

        with st.spinner("🤖 正在分析..."):
            scenes = analyze_script(text_input, api_key)
            
        if scenes:
            st.success(f"分析完成！开始画图...")
            result_container = st.container()
            for i, scene in enumerate(scenes):
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"**#{i+1}**")
                        st.write(scene['script'])
                    with c2:
                        img_res = generate_image(scene['prompt'], api_key)
                        if isinstance(img_res, str):
                            st.warning("⚠️ 画图失败")
                            st.caption(img_res[-100:])
                        else:
                            st.image(img_res)
                st.divider()
