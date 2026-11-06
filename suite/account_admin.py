"""Shared admin-managed accounts. Passwords remain hashes; history is append-only."""
import sqlite3
from .demo_accounts import hash_password,check_password,DEMO_USERS
from .common import bkk_now

ROLES=['admin','planning','supervisor','operator','management','production']


def change(db,actor,action,username,password='',role='operator',display=''):
    username=str(username).strip()
    if not username or len(username)>80:raise ValueError('Enter a username (1–80 characters)')
    with sqlite3.connect(db,timeout=15) as con:
        con.execute('BEGIN IMMEDIATE')
        admin=con.execute('SELECT role,active FROM users WHERE lower(username)=lower(?)',(actor,)).fetchone()
        if not admin or admin[0]!='admin' or not admin[1]:raise ValueError('Active administrator required')
        con.execute('CREATE TABLE IF NOT EXISTS account_admin_history(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,username TEXT,recorded_at TEXT)')
        row=con.execute('SELECT id,role,active FROM users WHERE lower(username)=lower(?)',(username,)).fetchone()
        if action=='Create':
            if row:raise ValueError('Username already exists; reactivate it instead')
            if role not in ROLES:raise ValueError('Invalid role')
            if not password:raise ValueError('Enter a password')
            con.execute('INSERT INTO users(username,password_hash,role,display_name,active,created_at) VALUES(?,?,?,?,1,CURRENT_TIMESTAMP)',(username,hash_password(password),role,display.strip() or username))
        else:
            if not row:raise ValueError('Account not found')
            if action=='Reset password':
                if not password:raise ValueError('Enter a new password')
                con.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(password),row[0]))
            elif action in ('Remove / deactivate','Reactivate'):
                if action=='Remove / deactivate' and row[1]=='admin' and row[2] and con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:raise ValueError('Cannot remove the last active administrator')
                con.execute('UPDATE users SET active=? WHERE id=?',(int(action=='Reactivate'),row[0]))
            else:raise ValueError('Unsupported action')
        con.execute('INSERT INTO account_admin_history(actor,action,username,recorded_at) VALUES(?,?,?,?)',(actor,action,username,bkk_now().isoformat()))


def render(st,db,actor):
    import pandas as pd
    with sqlite3.connect(db) as con:
        admin=con.execute('SELECT role,active FROM users WHERE lower(username)=lower(?)',(actor,)).fetchone()
        if not admin or admin[0]!='admin' or not admin[1]:st.info('สำหรับผู้ดูแลระบบ / Administrator only');return
        rows=con.execute('SELECT username,display_name,role,active,password_hash FROM users ORDER BY username').fetchall()
    defaults={u:p for u,p,_,_ in DEMO_USERS}
    view=[]
    for username,display,role,active,digest in rows:
        default=defaults.get(username.lower());known=default and check_password(default,digest)
        view.append({'Username':username,'Name':display,'Role':role,'Active':bool(active),'Password':default if known else 'Custom password — use Reset'})
    st.dataframe(pd.DataFrame(view),hide_index=True,use_container_width=True)
    st.caption('แสดงรหัสเริ่มต้นเฉพาะที่ยังตรงกับบัญชี รหัสที่เปลี่ยนแล้วอ่านกลับไม่ได้ / Default passwords shown only when still valid; custom passwords can be reset.')
    with st.form('admin_account_change'):
        action=st.selectbox('จัดการ / Action',['Create','Reset password','Remove / deactivate','Reactivate'])
        username=st.text_input('ชื่อผู้ใช้ / Username')
        display=st.text_input('ชื่อแสดง / Display name')
        role=st.selectbox('สิทธิ์ / Role',ROLES)
        password=st.text_input('รหัสผ่านใหม่ / New password',type='password')
        submitted=st.form_submit_button('💾 บันทึก / Save')
    if submitted:
        try:change(db,actor,action,username,password,role,display);st.success('บันทึกแล้ว / Saved');st.rerun()
        except ValueError as exc:st.error(str(exc))
    st.caption('Remove disables login and preserves audit history. / ลบบัญชีโดยปิดการใช้งาน เก็บประวัติเดิม')

    with st.expander('ประวัติจัดการบัญชี / Account change history'):
        with sqlite3.connect(db) as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='account_admin_history'").fetchone():
                st.dataframe(pd.read_sql_query('SELECT actor,action,username,recorded_at FROM account_admin_history ORDER BY id DESC LIMIT 500',con),hide_index=True,use_container_width=True)
