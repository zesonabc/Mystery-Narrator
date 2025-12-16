import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator 2.5", layout="wide", page_icon="🍌")

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .stButton>button { background-color: #0080FF; color: white; border: none; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🍌 2.5 Flash Engine")
    api_key = st.text_input("Gemini API Key", type="password")
    st.info("Target Models (Based on screenshot):\n- Text: gemini-2.5-flash\n- Image: gemini-2.5-flash-image")

# ================= 核心逻辑 =================
def analyze_script(script, key):
    genai.configure(api_key=key)
    
    # 【文本模型】使用截图里的 "Gemini 2.5 Flash"
    # 相比 3.0 Pro，这个应该是免费的
    target_model = 'gemini-2.5-flash'
    
    try:
        model = genai.GenerativeModel(target_model)
        
        prompt = f"""
        You are a mystery video director.
        Script: {script}
        Task: Split script into scenes. Write an Image Prompt.
        Output JSON: [{{"script": "...", "prompt": "..."}}]
        """
        
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
        
    except Exception as e:
        st.error(f"文本分析失败 ({target_model}): {e}")
        return None

def generate_image(prompt, key):
    genai.configure(api_key=key)
    
    # 【画图模型】使用截图里的 "Nano Banana" (非Pro版)
    # ID: gemini-2.5-flash-image
    target_model = 'gemini-2.5-flash-image'
    
    try:
        model = genai.GenerativeModel(target_model)
        
        # 尝试调用 Nano Banana
        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9"
        )
        return result.images[0]._pil_image
    except Exception as e:
        return f"Nano Banana 报错: {str(e)}"

# ================= 主界面 =================
st.title("🍌 MysteryNarrator (Flash 2.5 Edition)")
st.caption("Environment: Gemini 2.5 Flash + Nano Banana")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 生成分镜与画面"):
    if not api_key:
        st.error("请填入 Key")
    else:
        with st.spinner("🤖 2.5 Flash 正在分析..."):
            scenes = analyze_script(text_input, api_key)
            
        if scenes:
            st.success(f"分析完成！正在调用 Nano Banana 画图...")
            
            result_container = st.container()
            
            for i, scene in enumerate(scenes):
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"**#{i+1}**")
                        st.write(scene['script'])
                        st.caption(scene['prompt'])
                    with c2:
                        img_res = generate_image(scene['prompt'], api_key)
                        if isinstance(img_res, str):
                            st.warning("⚠️ 画图未成功")
                            st.caption(img_res) # 显示具体报错
                        else:
                            st.image(img_res)
                st.divider()
