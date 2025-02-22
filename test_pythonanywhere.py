from flask import Flask,request, jsonify,render_template
import json
import sqlite3
import yaml
import datetime

app = Flask(__name__)
# database_url = os.environ.get('DATABASE_URL')

@app.route("/")
def hello():
    create_table()
    purchase_requisitions = get_purchase_requisition_list() 
    purchase_requisition_count = get_purchase_requisition_count()
    return render_template('index.html', purchase_requisitions=purchase_requisitions, purchase_requisition_count = purchase_requisition_count)

@app.route('/post_data', methods=['GET', 'POST'])
def check():
    if request.method == 'POST':
        data = request.json
        
        insert_data(data)
    else:
        data = 'no data'
    return data

def create_table():
    conn = sqlite3.connect('purchase_requisition.db')
    cur = conn.cursor()
    strSQL = """    
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
    conn = sqlite3.connect('purchase_requisition.db')
    cur = conn.cursor()
    # データを辞書型変数に格納する
    i_data = {}
    i_data.setdefault('document_id',data['document_id'])
    i_data.setdefault('document_title',data['document_title'])
    # データをタプル型変数に格納する
    insert_tuple = tuple(i_data.values()) + (json.dumps(data,ensure_ascii=False), ) 

    # データを挿入するSQLを構築する
    strSQL = """
        INSERT 
            INTO purchase_requisition( 
                document_id, 
                document_title, 
                json_data
            ) 
            VALUES ( 
                %s, 
                '%s', 
                '%s'
            )
        """
    strSQL = strSQL % insert_tuple
    cur.execute(strSQL)
    conn.commit()
    conn.close()

def get_purchase_requisition_count():
    conn = sqlite3.connect('purchase_requisition.db')
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

def get_purchase_requisition_list():
    conn = sqlite3.connect('purchase_requisition.db')
    cur = conn.cursor()
    strSQL = f"""
        Select
            document_id, 
            document_title, 
            created_at
        from purchase_requisition
        order by created_at desc
        limit 20;
    """
    cur.execute(strSQL)
    res = cur.fetchall()
    td = datetime.timedelta(hours=9)
    tbl_col = ['document_id', 'document_title', 'created_at']
    result = []
    for row in res:
        d_row = dict(zip(tbl_col,row))
        result.append(d_row)

    conn.close()

    return result 

if __name__ == '__main__':
    app.run(debug=True)