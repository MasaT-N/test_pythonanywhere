from flask import Flask, request, render_template, Response, redirect, url_for
import json
import sqlite3
import yaml
import datetime
import os
import sys
from pathlib import Path
import requests
import base64
import dateutil.parser
import zipfile
import io

app = Flask(__name__)
work_dir = Path(sys.argv[0]).parent


@app.route("/")
def hello():
    create_table()
    purchase_requisitions, factories = get_purchase_requisition_list()  # 戻り値を追加
    purchase_requisition_count = get_purchase_requisition_count()
    return render_template('index.html', purchase_requisitions=purchase_requisitions,
                           purchase_requisition_count=purchase_requisition_count, factories=factories)  # factoryを追加


@app.route('/post_data', methods=['GET', 'POST'])
def check():
    if request.method == 'POST':
        data = request.json
        insert_data(data)
    else:
        data = 'no data'
    return data


@app.route("/download/<int:document_id>")
def download(document_id):
    """
    指定された文書IDの添付ファイルをダウンロードする。

    Args:
        document_id (int): コラボフローの文書ID。

    Returns:
        Response: ダウンロードさせるZipファイルを返す。
    """
    setting_file = os.path.join(work_dir, 'setting.yaml')
    setting = read_setting(setting_file)
    zip_buffer = download_attachments(document_id, setting)

    if zip_buffer:
        zip_buffer.seek(0)
        response = Response(zip_buffer, mimetype='application/zip')
        response.headers['Content-Disposition'] = f'attachment; filename=document_{document_id}_attachments.zip'
        return response
    else:
        return f"No attachments found or error occurred for document ID {document_id}."
    
@app.route("/download/reload/<int:document_id>")
def download_reload(document_id):
    """
    指定された文書IDのレコードをダウンロード済みに更新し、一覧ページをリロードする。

    Args:
        document_id (int): コラボフローの文書ID。

    Returns:
        Response: リダイレクトさせる。
    """
    # ダウンロード処理が完了したら、ダウンロード済みとして更新
    update_downloaded(document_id)

    # ページをリロードする
    return redirect(url_for('hello'))


def create_table():
    db_path = os.path.join(work_dir, 'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # テーブルが存在するか確認するSQL
    strSQL = """
        SELECT name FROM sqlite_master WHERE type='table' AND name='purchase_requisition';
    """
    cur.execute(strSQL)
    res = cur.fetchone()

    # テーブルが存在しなければ作成する
    if res is None:
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
                downloaded integer DEFAULT 0, 
                created_at text DEFAULT CURRENT_TIMESTAMP
            );
        """
        cur.execute(strSQL)
        conn.commit()
    else:  # ダウンロードカラムが存在しない場合に、カラムを追加する
        strSQL = """
            SELECT downloaded FROM purchase_requisition LIMIT 1;
        """
        try:
            cur.execute(strSQL)
        except sqlite3.OperationalError as e:
            if 'no such column: downloaded' in str(e):
                print('downloaded column does not exist, adding...')
                strSQL = """
                    ALTER TABLE purchase_requisition ADD COLUMN downloaded INTEGER DEFAULT 0;
                """
                cur.execute(strSQL)
                conn.commit()
            else:
                raise e
    conn.close()


def update_downloaded(document_id):
    """
    指定された文書IDのレコードの downloaded フィールドを 1 に更新する。

    Args:
        document_id (int): 更新する文書ID。
    """
    db_path = os.path.join(work_dir, 'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    strSQL = f"""
        UPDATE purchase_requisition
        SET downloaded = 1
        WHERE document_id = {document_id};
    """
    cur.execute(strSQL)
    conn.commit()
    conn.close()


def insert_data(data):
    db_path = os.path.join(work_dir, 'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # データを辞書型変数に格納する
    i_data = {}
    i_data.setdefault('document_id', data['document_id'])
    i_data.setdefault('document_number', data['document_number'])
    i_data.setdefault('document_title', data['document_title'])
    i_data.setdefault('request_user', data['request_user']['name'])
    i_data.setdefault('request_group', data['request_group']['name'])
    i_data.setdefault('request_factory', data['contents']['fid16']['label'])
    i_data.setdefault('amount', data['contents']['fid3']['value'])
    i_data.setdefault('flow_status', data['flow_status'])
    i_data.setdefault('end_date', data['end_date'])

    # データをタプル型変数に格納する
    insert_tuple = tuple(i_data.values()) + (json.dumps(data, ensure_ascii=False),)

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
    db_path = os.path.join(work_dir, 'purchase_requisition.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    setting_file = os.path.join(work_dir, 'setting.yaml')
    setting = read_setting(setting_file)
    strSQL = f"""
        Select
            *
        from
        (
        Select
            document_id, 
            document_number, 
            document_title, 
            request_user, 
            request_group, 
            request_factory, 
            amount, 
            flow_status, 
            end_date,
            downloaded
        from purchase_requisition
        where
            downloaded = 0
        union all
        Select
            document_id, 
            document_number, 
            document_title, 
            request_user, 
            request_group, 
            request_factory, 
            amount, 
            flow_status, 
            end_date,
            downloaded
        from purchase_requisition
        where
            downloaded = 1
        limit {setting['limit']}
        ) as t
        order by end_date desc
        ;
    """
    cur.execute(strSQL)
    res = cur.fetchall()
    td = datetime.timedelta(hours=9)
    tbl_col = ['document_id', 'document_number', 'document_title', 'request_user', 'request_group', 'request_factory',
               'amount', 'flow_status', 'end_date', 'downloaded']
    result = []
    factories = set()  # 重複を削除するためのセットを作成

    for row in res:
        d_row = dict(zip(tbl_col, row))
        try:
            end_date = dateutil.parser.parse(d_row['end_date'])  # datetimeオブジェクトに変換
            end_date += td
            d_row['end_date'] = end_date.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError) as e:
            print(f"Error parsing date: {d_row['end_date']}, Error: {e}")
            d_row['end_date'] = None
        result.append(d_row)
        factories.add(d_row['request_factory'])  # request_factoryをセットに追加
    conn.close()
    return result, sorted(list(factories))  # セットをリストに変換してソートして返却


def get_purchase_requisition_count():
    db_path = os.path.join(work_dir, 'purchase_requisition.db')
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


def create_authorization_key(setting):
    """
    クライアント名とAPIキーをBASE64エンコードして認証キーを生成する。

    Args:
        setting (dict): 設定ファイルから読み込んだ設定情報。

    Returns:
        str: BASE64エンコードされた認証キー。
    """
    client_name = setting['collaboflow']['client_name']
    api_key = setting['collaboflow']['api_key']
    auth_string = f"{client_name}/apikey:{api_key}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")
    return f"Basic {auth_base64}"


def read_setting(yaml_path):
    with open(yaml_path, 'r', encoding='utf-8') as f:
        setting = yaml.safe_load(f)
    setting['collaboflow']['authorization_key'] = create_authorization_key(setting)
    return setting


def download_attachments(document_id, setting):
    """
    コラボフローのREST APIから添付ファイルをダウンロードし、Zip圧縮して返す。

    Args:
        document_id (int): コラボフローの文書ID。
        setting (dict): 設定ファイルから読み込んだ設定情報。

    Returns:
        io.BytesIO: Zip圧縮されたファイルデータ。
    """
    api_base_url = setting['collaboflow']['api_base_url']
    tenant_id = setting['collaboflow']['tenant_id']
    authorization_key = setting['collaboflow']['authorization_key']

    headers = {
        "X-Collaboflow-Authorization": authorization_key,
        "accept": "application/json",
    }

    api_url = f"{api_base_url}{tenant_id}/api/index.cfm"
    app_cd = setting['collaboflow']['app_cd']
    # 文書情報を取得
    document_url = f"{api_url}/v1/documents/{document_id}/contents?app_cd={app_cd}"

    try:
        response = requests.get(document_url, headers=headers)
        response.raise_for_status()
        document_data = response.json()
        # print(json.dumps(document_data, indent=4, ensure_ascii=False))
    except requests.exceptions.RequestException as e:
        print(f"Error getting document information: {e}")
        return None

    attachments_fields = ["fid6", "fid12"]
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for attachment_field in attachments_fields:
            if "link" in document_data["contents"][attachment_field] and document_data["contents"][attachment_field][
                "type"] == "attachment":
                file_binary = download_attachments_file(
                    document_id=document_id,
                    attachment_id=document_data["contents"][attachment_field]["value"],
                    file_name=document_data["contents"][attachment_field]["label"],
                    api_url=api_url,
                    authorization_key=authorization_key,
                )
                if file_binary:
                    zip_file.writestr(document_data["contents"][attachment_field]["label"], file_binary)
            else:
                print(f"No attachment found for document ID {document_id}(field: {attachment_field})")
    return zip_buffer


def download_attachments_file(document_id, attachment_id, file_name, api_url, authorization_key):
    """
    コラボフローのREST APIから添付ファイルをダウンロードする。

    Args:
        document_id (int): コラボフローの文書ID。
        attachment_id (int): 添付ファイルID。
        file_name (str): ダウンロードするファイル名。
        api_url (str): コラボフローのAPIのURL。
        authorization_key (str): 認証キー。

    Returns:
        byte: ダウンロードしたファイルのバイナリ。
    """
    attachment_url = f"{api_url}/v1/files/{attachment_id}/download"

    headers = {
        "X-Collaboflow-Authorization": authorization_key,
    }
    try:
        response = requests.get(attachment_url, headers=headers, stream=True)
        response.raise_for_status()
        if response.status_code == 200:
            # ファイルバイナリを取得
            file_binary = response.content
            print(f"Downloaded: {file_name} (binary data)")
            return file_binary
        else:
            print(f"Error downloading attachment {file_name}: Status code {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading attachment {file_name}: {e}")
    return None


if __name__ == "__main__":
    # webサーバー立ち上げ
    app.run()
