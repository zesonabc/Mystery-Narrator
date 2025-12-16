import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import requests # 👈 我们改用这个直接发请求
import base64
import io
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator HTTP", layout="wide", page_icon="🍌")
st.markdown("""<style>.stApp { background-color: #050505; color: #ccc; }</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🍌 HTTP Bypass Engine")
    api_key = st.text_input("Gemini API Key", type="password")
    st.info("模式：绕过 Python 库，直接发送 HTTP 网络请求")

# ================= 核心逻辑 =================

def analyze_script(script, key):
    """文本分析还是可以用库的，因为文本功能不报错"""
    if not key: return None
    genai.configure(api_key=key)
    try:
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
        prompt = f"""
        You are a mystery video director. Script: {script}
        Output JSON Array: [{{"script": "...", "prompt": "..."}}]
        """
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except:
        # 如果 JSON 模式失败，尝试普通模式清洗
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(prompt)
            import re
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            return json.loads(match.group()) if match else None
        except Exception as e:
            st.error(f"文本分析失败: {e}")
            return None

def generate_image_http(prompt, key):
    """
    🔥 核心大招：直接用 HTTP 请求绕过 Python 库的版本限制
    """
    # 尝试 1: 使用你截图里的 Nano Banana (Gemini 2.5 Flash Image)
    # URL 格式: https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:predict?key={KEY}
    
    # 优先尝试的模型列表
    models_to_try = [
        "gemini-2.5-flash-image",
        "imagen-3.0-generate-001"
    ]

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict?key={key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # 构造请求数据
        data = {
            "instances": [
                {
                    "prompt": prompt
                }
            ],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "16:9"
