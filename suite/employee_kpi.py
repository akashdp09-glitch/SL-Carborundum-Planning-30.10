"""Traceable employee-specific KPI definitions and period evidence."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd
from .common import bkk_now

PERIODS = ("Weekly", "Monthly", "Quarterly", "Yearly", "Custom")


def init_db(db_path):
    p=Path(db_path); p.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(p,timeout=20) as con:
        con.execute("PRAGMA busy_timeout=20000")
        con.execute("""CREATE TABLE IF NOT EXISTS employee_kpi_definitions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT NOT NULL, owner TEXT NOT NULL,
          target REAL NOT NULL, unit TEXT NOT NULL, direction TEXT NOT NULL, method TEXT NOT NULL,
          definition TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
          created_at TEXT NOT NULL, retired_by TEXT NOT NULL DEFAULT '', retired_at TEXT NOT NULL DEFAULT '')""")
        con.execute("""CREATE TABLE IF NOT EXISTS employee_kpi_evidence(
          id INTEGER PRIMARY KEY AUTOINCREMENT, definition_id INTEGER NOT NULL, period_type TEXT NOT NULL,
          period_start TEXT NOT NULL, period_end TEXT NOT NULL, numerator REAL NOT NULL,
          denominator REAL NOT NULL, actual REAL NOT NULL, evidence_ref TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
          recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL,
          FOREIGN KEY(definition_id) REFERENCES employee_kpi_definitions(id))""")
        con.execute("CREATE INDEX IF NOT EXISTS ix_employee_kpi_period ON employee_kpi_evidence(definition_id,period_start,period_end,id)")
        con.execute("""CREATE TABLE IF NOT EXISTS employee_kpi_definition_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, definition_id INTEGER NOT NULL, event TEXT NOT NULL,
          user_name TEXT NOT NULL, event_at TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '')""")


def add_definition(db_path, name, owner, target, unit, direction, method, definition, user):
    name=str(name or '').strip(); owner=str(owner or '').strip(); unit=str(unit or '').strip()
    if not name or not owner or not unit: raise ValueError('KPI name, employee/owner, and unit are required.')
    target=float(target)
    if target<0: raise ValueError('Target cannot be negative.')
    if direction not in ('Higher is better','Lower is better'): raise ValueError('Invalid target direction.')
    if method not in ('Percentage (numerator ÷ denominator)','Numeric actual'): raise ValueError('Invalid calculation method.')
    if not str(definition or '').strip(): raise ValueError('Write the measurable definition and accepted evidence source.')
    init_db(db_path); stamp=bkk_now().isoformat(timespec='seconds')
    with sqlite3.connect(db_path,timeout=20) as con:
        con.execute('PRAGMA busy_timeout=20000')
        cur=con.execute('INSERT INTO employee_kpi_definitions(name,owner,target,unit,direction,method,definition,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(name,owner,target,unit,direction,method,str(definition).strip(),str(user or 'Unknown'),stamp))
        kid=int(cur.lastrowid); code=f'EKPI-{kid:04d}'; con.execute('UPDATE employee_kpi_definitions SET code=? WHERE id=?',(code,kid)); con.execute('INSERT INTO employee_kpi_definition_events(definition_id,event,user_name,event_at,detail) VALUES(?,?,?,?,?)',(kid,'CREATED',str(user or 'Unknown'),stamp,f'{name} | {owner} | target={target} {unit}'))
    return {'id':kid,'code':code,'created_at':stamp}


def retire_definition(db_path, definition_id, user='Unknown'):
    init_db(db_path); stamp=bkk_now().isoformat(timespec='seconds')
    with sqlite3.connect(db_path,timeout=20) as con:
        con.execute('PRAGMA busy_timeout=20000')
        row=con.execute('SELECT name,owner,active FROM employee_kpi_definitions WHERE id=?',(int(definition_id),)).fetchone()
        if not row: raise ValueError('KPI definition was not found.')
        if not row[2]: return False
        con.execute('UPDATE employee_kpi_definitions SET active=0,retired_by=?,retired_at=? WHERE id=?',(str(user or 'Unknown'),stamp,int(definition_id)))
        con.execute('INSERT INTO employee_kpi_definition_events(definition_id,event,user_name,event_at,detail) VALUES(?,?,?,?,?)',(int(definition_id),'RETIRED',str(user or 'Unknown'),stamp,f'{row[0]} | {row[1]}'))
    return True


def add_measurement(db_path, definition_id, period_type, start, end, numerator, denominator, evidence, notes='', user=''):
    if period_type not in PERIODS: raise ValueError('Choose a supported reporting period.')
    start=pd.Timestamp(start).date(); end=pd.Timestamp(end).date()
    if end<start: raise ValueError('Period end must be on or after period start.')
    n=float(numerator); d=float(denominator)
    if n<0 or d<=0: raise ValueError('Actual/numerator must be non-negative and denominator must be greater than zero.')
    ev=str(evidence or '').strip()
    if not ev: raise ValueError('Evidence is required (report/workbook/date or record IDs).')
    init_db(db_path); stamp=bkk_now().isoformat(timespec='seconds')
    with sqlite3.connect(db_path,timeout=20) as con:
        con.execute('PRAGMA busy_timeout=20000')
        m=con.execute('SELECT method FROM employee_kpi_definitions WHERE id=? AND active=1',(int(definition_id),)).fetchone()
        if not m: raise ValueError('KPI definition is not active.')
        if m[0].startswith('Percentage') and n>d: raise ValueError('For percentage KPIs, numerator cannot exceed denominator.')
        actual=n/d*100.0 if m[0].startswith('Percentage') else n
        cur=con.execute('INSERT INTO employee_kpi_evidence(definition_id,period_type,period_start,period_end,numerator,denominator,actual,evidence_ref,notes,recorded_by,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(int(definition_id),period_type,start.isoformat(),end.isoformat(),n,d,actual,ev,str(notes or '').strip(),str(user or 'Unknown'),stamp))
        event_id=int(cur.lastrowid)
    return {'id':event_id,'actual':actual,'recorded_at':stamp}


def definitions(db_path, active_only=True):
    init_db(db_path)
    sql='SELECT * FROM employee_kpi_definitions'+(' WHERE active=1' if active_only else '')+' ORDER BY owner,name,id'
    with sqlite3.connect(db_path,timeout=20) as con: return pd.read_sql_query(sql,con)


def measurements(db_path):
    init_db(db_path)
    q='''SELECT e.id,e.period_type AS Period,e.period_start AS [From],e.period_end AS [To],d.code AS Code,d.name AS KPI,d.owner AS Employee,d.target AS Target,d.unit AS Unit,d.direction AS Direction,d.method AS Method,e.actual AS Actual,e.numerator AS Numerator,e.denominator AS Denominator,e.evidence_ref AS Evidence,e.notes AS Notes,e.recorded_by AS RecordedBy,e.recorded_at AS RecordedAt,d.id AS DefinitionID FROM employee_kpi_evidence e JOIN employee_kpi_definitions d ON d.id=e.definition_id ORDER BY e.period_start DESC,d.owner,d.name,e.id DESC'''
    with sqlite3.connect(db_path,timeout=20) as con: df=pd.read_sql_query(q,con)
    if df.empty:return df
    df['Result']=df.apply(lambda r:'MEETS TARGET' if (r['Actual']>=r['Target'] if r['Direction']=='Higher is better' else r['Actual']<=r['Target']) else 'BELOW TARGET',axis=1)
    def attainment(r):
        if r['Direction']=='Higher is better': return 100.0 if r['Target']==0 and r['Actual']>=0 else min(100.0,float(r['Actual'])/float(r['Target'])*100) if r['Target'] else 0.0
        return 100.0 if r['Actual']<=r['Target'] else (0.0 if r['Actual']==0 else min(100.0,float(r['Target'])/float(r['Actual'])*100))
    df['Target attainment %']=df.apply(attainment,axis=1).round(1)
    return df


def render_custom(st, db_path, *, can_edit=False, user='Unknown'):
    st.divider(); st.subheader('👤 Employee-specific KPI — Weekly / Monthly / Quarterly / Yearly')
    st.caption('Create measurable KPIs per employee. The software calculates results from entered numerator/denominator or numeric actual; every measurement requires evidence and is append-only. For a revised target, create a new KPI definition so prior records remain traceable.')
    init_db(db_path)
    defs=definitions(db_path,active_only=False)
    if can_edit:
        with st.expander('Create employee KPI / KPI ใหม่รายบุคคล',expanded=False):
            with st.form('employee_kpi_definition_form',clear_on_submit=True):
                c1,c2,c3=st.columns(3)
                name=c1.text_input('KPI name'); owner=c2.text_input('Employee / owner'); target=c3.number_input('Target',min_value=0.0,value=1.0,step=1.0)
                c4,c5=st.columns(2)
                unit=c4.text_input('Unit (%, pcs, days, hours, THB)')
                direction=c5.selectbox('Direction',['Higher is better','Lower is better'])
                method=st.selectbox('Calculation',['Percentage (numerator ÷ denominator)','Numeric actual'])
                definition=st.text_area('Exact rule and evidence source')
                make=st.form_submit_button('Save KPI definition',type='primary')
            if make:
                try:
                    saved=add_definition(db_path,name,owner,target,unit,direction,method,definition,user)
                    st.success(f"Saved {saved['code']}. Definition is traceable and ready for evidence.");st.rerun()
                except Exception as e:st.error(f'Not saved: {e}')
    active=defs[defs['active'].astype(bool)] if not defs.empty else defs
    if can_edit and not active.empty:
        st.markdown('##### Record a result')
        options={f"{r.code} — {r.owner} — {r.name}":int(r.id) for r in active.itertuples()}
        selected=st.selectbox('Employee KPI',list(options),key='employee_kpi_selected'); item=active[active['id'].eq(options[selected])].iloc[0]
        today=bkk_now().date(); monday=today-pd.Timedelta(days=today.weekday()); sunday=monday+pd.Timedelta(days=6)
        with st.form('employee_kpi_evidence_form',clear_on_submit=True):
            c1,c2,c3=st.columns(3)
            period=c1.selectbox('Period type',PERIODS,key='employee_kpi_period_type')
            start=c2.date_input('Period start',value=monday if period=='Weekly' else today.replace(day=1),key='employee_kpi_start')
            end=c3.date_input('Period end',value=sunday if period=='Weekly' else today,key='employee_kpi_end')
            if str(item['method']).startswith('Percentage'):
                c4,c5=st.columns(2); n=c4.number_input('Numerator',min_value=0.0,value=0.0,step=1.0); d=c5.number_input('Denominator',min_value=0.0,value=0.0,step=1.0)
            else:
                n=st.number_input(f"Actual ({item['unit']})",min_value=0.0,value=0.0,step=1.0); d=1.0
            ev=st.text_input('Evidence (source report / date / record IDs)'); notes=st.text_input('Notes')
            save=st.form_submit_button('Save measured result',type='primary')
        if save:
            try:
                saved=add_measurement(db_path,int(item['id']),period,start,end,n,d,ev,notes,user)
                st.success(f"Saved {saved['actual']:.2f} {item['unit']} · evidence event #{saved['id']} · {saved['recorded_at']} Thailand local time.");st.rerun()
            except Exception as e:st.error(f'Not saved: {e}')
    if not defs.empty:
        show=defs.rename(columns={'code':'Code','name':'KPI','owner':'Employee','target':'Target','unit':'Unit','direction':'Direction','method':'Calculation','definition':'Rule / measurement evidence','active':'Active','created_by':'Created by','created_at':'Created at (Thailand local time — Phan Thong, Chonburi)'})
        st.dataframe(show[['Code','KPI','Employee','Target','Unit','Direction','Calculation','Rule / measurement evidence','Active','Created by','Created at (Thailand local time — Phan Thong, Chonburi)']],use_container_width=True,hide_index=True)
        if can_edit and not active.empty:
            with st.form('employee_kpi_retire_form'):
                retire_choice=st.selectbox('Retire KPI definition (keeps history)',[f"{r.code} — {r.owner} — {r.name}" for r in active.itertuples()],key='employee_kpi_retire_select')
                retire=st.form_submit_button('Retire selected KPI')
            if retire:
                try:
                    retire_id=next(int(r.id) for r in active.itertuples() if retire_choice.startswith(str(r.code)))
                    retire_definition(db_path,retire_id,user);st.success('KPI retired. Existing measurements remain in history.');st.rerun()
                except Exception as e:st.error(f'KPI was not retired: {e}')
    data=measurements(db_path)
    if not data.empty:
        st.markdown('##### Results and revision history')
        st.dataframe(data.drop(columns=['DefinitionID']),use_container_width=True,hide_index=True,height=360)
        st.download_button('⬇ Export employee KPI evidence CSV',data.drop(columns=['DefinitionID']).to_csv(index=False).encode('utf-8-sig'),'Employee_KPI_Evidence.csv','text/csv',key='employee_kpi_csv')
    if not can_edit: st.caption('Read-only. KPI definitions and results require an authorized editing role.')
