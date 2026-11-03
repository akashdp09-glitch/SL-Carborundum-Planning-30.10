"""Plan2026 actual-by-process sheet explorer: evidence only, no guessed mappings."""
import io
import pandas as pd

def render(st):
    st.subheader('📚 Plan2026 process-sheet actual evidence / หลักฐานผลผลิตจริง')
    st.caption('Upload the ORIGINAL current Plan2026 workbook. Process sheets may have different headers; verify actual-quantity and date columns before use. This view never substitutes an unverified sheet for Production-confirmed actuals.')
    upload=st.file_uploader('Plan2026 workbook / ไฟล์แผน',type=['xlsx','xlsm'],key='process_actual_upload')
    if upload is None:return
    try:
        xls=pd.ExcelFile(io.BytesIO(upload.getvalue()),engine='openpyxl')
        names=xls.sheet_names
        options=[s for s in names if any(w in s.lower() for w in ['pack','prepar','mix','form','fire','kiln','grind','cut'])]
        if not options:options=names
        sheet=st.selectbox('Process sheet / ชีตกระบวนการ',options,key='process_actual_sheet')
        df=pd.read_excel(xls,sheet_name=sheet,header=0)
        df=df.dropna(how='all').dropna(axis=1,how='all')
        st.caption(f'{len(df):,} nonblank rows; source sheet: {sheet}')
        cols=['-- select --']+list(map(str,df.columns))
        c1,c2,c3=st.columns(3)
        with c1:wo=c1.selectbox('WO column',cols,key='pa_wo')
        with c2:qty=c2.selectbox('ACTUAL quantity column (verify units)',cols,key='pa_qty')
        with c3:dt=c3.selectbox('ACTUAL date column',cols,key='pa_date')
        if qty!='-- select --':
            q=pd.to_numeric(df[qty],errors='coerce');st.metric('Selected actual quantity — SOURCE UNIT',f'{q.sum():,.2f}')
            st.warning('Do not interpret as pcs, kg or tonnes until unit and duplicated/summary rows are verified.')
        st.dataframe(df.head(300),use_container_width=True,height=400)
        st.download_button('⬇️ Export inspected sheet CSV',df.to_csv(index=False).encode('utf-8-sig'),file_name='Plan2026_'+sheet.replace('/','_')+'_evidence.csv',mime='text/csv',key='pa_csv')
    except Exception as e:st.error(f'Unable to read selected sheet: {e}')
