# Headless smoke test of the Planning Suite page with a stubbed Streamlit. Usage: set SL_TEST_FILES=<folder with Plan_2026-2-Update-021026.xlsx, Stock_on_hand_021026.xlsx, MRP_BOND2026-10.xlsx>  then python suite/smoke_test_headless.py (run from the program folder).
import sys,types,datetime as dt,shutil,os
from unittest.mock import MagicMock
from pathlib import Path
st=MagicMock(); 
st.cache_data=lambda *a,**k:(lambda f:f)
def _col():
    c=MagicMock(); c.number_input=lambda label,mn,mx,v=None,**k:v; return c
st.columns=lambda n:[_col() for _ in range(n if isinstance(n,int) else len(n))]
st.tabs=lambda l:[MagicMock() for _ in l]
st.date_input=lambda label,v,**k:v
st.number_input=lambda label,mn,mx,v=None,**k:v
st.selectbox=lambda label,opts,index=0,**k:opts[index]
st.radio=lambda l,o,**k:o[0]
st.text_input=lambda l,v='',**k:v
st.file_uploader=lambda *a,**k:None
st.button=lambda *a,**k:False
st.sidebar=MagicMock()
sys.modules['streamlit']=st; sys.modules['streamlit.components']=MagicMock(); sys.modules['streamlit.components.v1']=MagicMock()
sys.path.insert(0,'.')
from suite import suite_page
U=Path(os.environ.get('SL_TEST_FILES','.')); D=Path('/tmp/smokedata'); D.mkdir(exist_ok=True)
shutil.copy(U/'MRP_BOND2026-10.xlsx',D/'Bond-MRP-LATEST.xlsx')
files={'Plan-2026-LATEST.xlsx':U/'Plan_2026-2-Update-021026.xlsx','Stock-on-Hand-LATEST.xlsx':U/'Stock_on_hand_021026.xlsx'}
fp=lambda n:files.get(n)
os.environ['SL_DB_PATH']=os.environ.get('SL_DB_PATH','sl_planning.db')
st.date_input=lambda label,v,**k:(dt.date(2026,10,3) if 'today' in label else v)
suite_page.render(fp,D,Path('/tmp/smokeshared'),None,'tester')
print('RENDER OK; errors:',st.error.call_args_list, '| downloads:',st.download_button.call_count)
suite_page.install_f1(Path('.')); print('F1 OK')
