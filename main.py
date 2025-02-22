from flask import Flask,request, render_template
import json
import sqlite3
import yaml
import datetime
import os
import sys
from pathlib import Path

app = Flask(__name__)
work_dir = Path(sys.argv[0]).parent

@app.route("/")
def hello():
    purchase_requisitions = get_purchase_requisition_list() 
    purchase_requisition_count = get_purchase_requisition_count()
    return render_template('index.html', purchase_requisitions=purchase_requisitions, purchase_requisition_count = purchase_requisition_count)

@app.route('/post_data', methods=['GET', 'POST'])
def check():
    if request.method == 'POST':
        data = request.json
        create_table()
        insert_data(data)
    else:
        data = 'no data'
    return data

def create_table():
    db_path = os.path.join(work_dir,'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    strSQL = """    
        CREATE TABLE purchase_requisition( 
            document_id integer PRIMARY KEY, 
            document_number text,
            document_title text,
            request_user text,
            request_group text,
            request_factory text,
            amount integer default 0,
            flow_status text,
            end_date text,    
            json_data text, 
            created_at text DEFAULT CURRENT_TIMESTAMP
        )
    """
    cur.execute(strSQL)
    conn.commit()
    conn.close()

def insert_data(data):
    db_path = os.path.join(work_dir,'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # データを辞書型変数に格納する
    i_data = {}
    i_data.setdefault('document_id',data['document_id'])
    i_data.setdefault('document_number',data['document_number'])
    i_data.setdefault('document_title',data['document_title'])
    i_data.setdefault('request_user',data['request_user']['name'])
    i_data.setdefault('request_group',data['request_group']['name'])
    i_data.setdefault('request_factory',data['contents']['fid16']['label'])
    i_data.setdefault('amount',data['contents']['fid3']['value'])
    i_data.setdefault('flow_status',data['flow_status'])
    i_data.setdefault('end_date',data['end_date'])

    # データをタプル型変数に格納する
    insert_tuple = tuple(i_data.values()) + (json.dumps(data,ensure_ascii=False), ) 

    # データを挿入するSQLを構築する
    strSQL = """
        INSERT 
            INTO purchase_requisition( 
                document_id, 
                document_number, 
                document_title, 
                request_user, 
                request_group, 
                request_factory, 
                amount, 
                flow_status, 
                end_date, 
                json_data
            ) 
            SELECT
                * 
            FROM
                ( 
                    VALUES ( 
                        %s, 
                        '%s', 
                        '%s', 
                        '%s', 
                        '%s', 
                        '%s', 
                        %s, 
                        '%s', 
                        '%s', 
                        '%s'
                    )
                ) AS new ( 
                    document_id, 
                    document_number, 
                    document_title, 
                    request_user, 
                    request_group, 
                    request_factory, 
                    amount, 
                    flow_status, 
                    end_date, 
                    json_data
                ) 
            WHERE
                NOT EXISTS ( 
                    SELECT
                        * 
                    FROM
                        purchase_requisition 
                    WHERE
                        document_id = new.document_id
                );
        """
    strSQL = strSQL % insert_tuple
    cur.execute(strSQL)
    conn.commit()
    conn.close()


def get_purchase_requisition_list():
    db_path = os.path.join(work_dir,'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    setting_file = os.path.join(work_dir,'setting.yaml')
    setting = read_setting(setting_file)
    strSQL = f"""
        Select
            document_id, 
            document_number, 
            document_title, 
            request_user, 
            request_group, 
            request_factory, 
            amount, 
            flow_status, 
            end_date
        from purchase_requisition
        order by end_date desc
        limit {setting['limit']};
    """
    cur.execute(strSQL)
    res = cur.fetchall()
    td = datetime.timedelta(hours=9)
    tbl_col = ['document_id', 'document_number', 'document_title', 'request_user', 'request_group', 'request_factory', 'amount', 'flow_status', 'end_date']
    for row in res:
        d_row = dict(zip(tbl_col,row))
        d_row['end_date'] = datetime.datetime.strptime(d_row['end_date'],'%Y-%m-%d %H:%M:%S') + td
    conn.close()
    return d_row 
        
def get_purchase_requisition_count():
    db_path = os.path.join(work_dir,'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    strSQL = f"""
        Select
            count(*)
        from purchase_requisition;
    """
    cur.execute(strSQL)
    res = cur.fetchone()
    conn.close()
    return res[0]         

def read_setting(yaml_path):
    with open(yaml_path,'r',encoding='utf-8') as f:       
        return yaml.safe_load(f)
            

if __name__ == "__main__":
    # webサーバー立ち上げ
    app.run()
