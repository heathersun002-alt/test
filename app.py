import streamlit as st
import pandas as pd
import PyPDF2
import docx
import io
import os  # <--- 必须导入 os 库来读取文件夹
from openai import OpenAI

# ==========================================
# 0. 初始化与工具函数
# ==========================================

DEFAULT_DB_FILE = "data.xlsx"
TEMPLATE_DIR = "templates"  # <--- 定义模板文件夹名称

# 初始化 Session State
if 'db_data' not in st.session_state:
    st.session_state['db_data'] = None
if 'templates' not in st.session_state:
    st.session_state['templates'] = {}


def extract_text_from_file(file_obj, file_name):
    """
    通用文本提取函数
    file_obj: 可以是 UploadedFile 对象，也可以是 open() 打开的文件对象
    file_name: 文件名 (用于判断类型)
    """
    try:
        name = file_name.lower()

        # 1. PDF 处理
        if name.endswith('.pdf'):
            reader = PyPDF2.PdfReader(file_obj)
            text = ""
            max_pages = 20
            for i, page in enumerate(reader.pages):
                if i >= max_pages: break
                text += page.extract_text()
            return text

        # 2. DOCX 处理
        elif name.endswith('.docx'):
            doc = docx.Document(file_obj)
            text = "\n".join([para.text for para in doc.paragraphs])
            return text[:20000]

        # 3. TXT 处理
        elif name.endswith('.txt'):
            # 如果是 bytes (上传的文件)，解码；如果是 str (本地读取)，直接用
            content = file_obj.read()
            if isinstance(content, bytes):
                return content.decode('utf-8')[:20000]
            return content[:20000]

        else:
            return ""
    except Exception as e:
        return f"读取错误: {e}"


def call_deepseek_audit(api_key, bond_info, template_text, target_text):
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    system_prompt = """
    你是一名资深的金融合规审核员。请基于【事实数据】和【标准模板】，对【待审核公告】进行严格审查。
    输出 Markdown 报告，包含：1.🔴风险提示 2.⚠️格式预警 3.🟢合规项
    """

    user_content = f"""
    【事实数据】
    {bond_info}

    【标准模板】
    {template_text[:3000]}...

    【待审核公告】
    {target_text}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ DeepSeek 调用失败: {e}"


# ==========================================
# 1. 侧边栏：配置区
# ==========================================
st.set_page_config(layout="wide", page_title="债券公告审核系统")

st.set_page_config(layout="wide", page_title="债券公告审核系统")

with st.sidebar:
    st.title("🐋 智能审核系统")

    # --- API Key ---
    api_key = None
    try:
        if "DEEPSEEK_API_KEY" in st.secrets:
            api_key = st.secrets["DEEPSEEK_API_KEY"]
            st.success("✅ 云端 Key 已连接")
    except:
        pass
    if not api_key:
        api_key = st.text_input("DeepSeek API Key", type="password")

    st.markdown("---")
    st.subheader("1. 债券数据库管理")

    # --- 逻辑修改：先尝试自动加载，但允许随时覆盖 ---

    # 如果 Session 为空，才去尝试自动加载一次
    if st.session_state['db_data'] is None:
        try:
            try:
                # 优先尝试 Excel
                df_local = pd.read_excel(DEFAULT_DB_FILE, engine='openpyxl')
            except:
                # 其次尝试 CSV
                df_local = pd.read_csv(DEFAULT_DB_FILE)

            df_local = df_local.astype(str)
            st.session_state['db_data'] = df_local
            # 存一个标记，告诉界面这是内置数据
            st.session_state['data_source'] = f"📂 内置: {DEFAULT_DB_FILE}"
        except:
            st.session_state['data_source'] = "无数据"

    # 显示当前状态
    if st.session_state['db_data'] is not None:
        st.success(f"✅ 当前数据源: {st.session_state.get('data_source', '未知')}")
        st.caption(f"包含记录: {len(st.session_state['db_data'])} 条")
    else:
        st.warning("⚠️ 暂无数据")

    # === 关键修改：上传按钮永远显示，用于覆盖更新 ===
    uploaded_db = st.file_uploader("📤 上传新表以更新/覆盖", type=['xlsx', 'csv'])

    if uploaded_db:
        try:
            if uploaded_db.name.endswith('.csv'):
                df_new = pd.read_csv(uploaded_db)
            else:
                df_new = pd.read_excel(uploaded_db, engine='openpyxl')

            # 更新 Session
            st.session_state['db_data'] = df_new.astype(str)
            st.session_state['data_source'] = f"📄 上传: {uploaded_db.name}"
            st.success("数据库已更新！")
            # 强制刷新页面以应用新数据
            st.rerun()
        except Exception as e:
            st.error(f"读取失败: {e}")

    st.markdown("---")
    st.subheader("2. 模板库管理")

    # 自动扫描 (逻辑不变)
    if not st.session_state['templates']:
        if os.path.exists(TEMPLATE_DIR):
            files = os.listdir(TEMPLATE_DIR)
            for f_name in files:
                if f_name.startswith("~") or f_name.startswith("."): continue
                full_path = os.path.join(TEMPLATE_DIR, f_name)
                try:
                    with open(full_path, "rb") as f:
                        content = extract_text_from_file(f, f_name)
                        if content: st.session_state['templates'][f_name] = content
                except: pass

    # 显示现有模板
    tpl_keys = list(st.session_state['templates'].keys())
    if tpl_keys:
        st.write(f"📚 当前可用模板 ({len(tpl_keys)}个)：")
        # 用 expander 折叠一下，防止列表太长
        with st.expander("点击查看列表"):
            for k in tpl_keys:
                st.caption(f"📄 {k}")
    else:
        st.warning("⚠️ 暂无模板")

    # === 关键修改：添加模板永远可用 ===
    st.caption("需要增加新模板？")
    with st.popover("➕ 上传新模板"):
        name = st.text_input("模板名称", placeholder="例如: 2026新规模板")
        file = st.file_uploader("文件", type=['txt', 'pdf', 'docx'])
        if st.button("确认添加"):
            if name and file:
                st.session_state['templates'][name] = extract_text_from_file(file, file.name)
                st.success(f"已添加: {name}")
                st.rerun()

# ==========================================
# 2. 主界面
# ==========================================
st.title("🚀 债券存续期公告审核 (DeepSeek)")

if not api_key:
    st.warning("👈 请输入 API Key")
    st.stop()

if st.session_state['db_data'] is None:
    st.info("👈 请加载数据库")
    st.stop()

# 业务逻辑
col1, col2 = st.columns(2)
with col1:
    df = st.session_state['db_data']
    search_col = st.selectbox("检索字段", df.columns, index=0)
    selected_val = st.selectbox("选择债券", df[search_col].unique())
    bond_row = df[df[search_col] == selected_val].iloc[0].to_dict()

with col2:
    st.json(bond_row)

st.markdown("---")
# 选择模板
if not tpl_keys:
    st.error("无可用模板，请检查 templates 文件夹")
    st.stop()

selected_tpl_name = st.selectbox("选择审核依据的模板", tpl_keys)
tpl_content = st.session_state['templates'][selected_tpl_name]

# 上传并运行
target_file = st.file_uploader("上传待审核公告", type=['pdf', 'docx'])

if st.button("🚀 开始审核", type="primary"):
    if target_file:
        with st.spinner("DeepSeek 正在分析..."):
            target_text = extract_text_from_file(target_file, target_file.name)
            res = call_deepseek_audit(api_key, str(bond_row), tpl_content, target_text)
        st.success("完成！")
        st.markdown(res)

