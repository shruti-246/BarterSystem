#from flask import Flask, request, jsonify
#import sqlite3
#from flask_cors import CORS
#from datetime import datetime
#import random

#def generate_code():
    #return ''.join([str(random.randint(0,9)) for _ in range(16)])


#app = Flask(__name__)
#CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
#DATABASE = 'barter.db'
import os
from flask import Flask, request, jsonify
from flask import render_template
import sqlite3
from flask_cors import CORS
from datetime import datetime
import random

def generate_code():
    return ''.join([str(random.randint(0,9)) for _ in range(16)])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
DB_PATH = os.path.join(BASE_DIR, "barter.db")

app = Flask(
    __name__,
    template_folder="../Frontend/templates",
    #static_folder="../Frontend/static"
)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

DATABASE = DB_PATH

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Setup DB and demo data
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.executescript('''
        DROP TABLE IF EXISTS user;
        DROP TABLE IF EXISTS item;
        DROP TABLE IF EXISTS trade;
        DROP TABLE IF EXISTS partnership;
        DROP TABLE IF EXISTS "transaction";  -- << fixed here
        DROP TABLE IF EXISTS ongoing_transaction;

        CREATE TABLE user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('buyer', 'seller')) NOT NULL
        );

        CREATE TABLE item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            condition TEXT,
            estimated_value REAL,
            available INTEGER DEFAULT 1,
            FOREIGN KEY(owner_id) REFERENCES user(id)
        );

        CREATE TABLE trade (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposer_id INTEGER,
            offered_item_id INTEGER,
            requested_item_id INTEGER,
            status TEXT CHECK(status IN ('pending', 'accepted', 'rejected')) DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(proposer_id) REFERENCES user(id),
            FOREIGN KEY(offered_item_id) REFERENCES item(id),
            FOREIGN KEY(requested_item_id) REFERENCES item(id)
        );

        INSERT INTO user (username, email, password, role) VALUES
            ('alice', 'alice@example.com', 'alicepass', 'seller'),
            ('bob', 'bob@example.com', 'bobpass', 'buyer');

        INSERT INTO item (owner_id, name, description, category, condition, estimated_value) VALUES
            (1, 'Guitar', 'An acoustic guitar', 'Music', 'Used', 100.0),
            (2, 'Camera', 'DSLR camera', 'Electronics', 'Like New', 250.0);

        CREATE TABLE partnership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            partner_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES user(id),
            FOREIGN KEY(partner_id) REFERENCES user(id)
        );

        CREATE TABLE "transaction" (  -- << quotes here
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            code TEXT NOT NULL,
            proposer_half TEXT NOT NULL,
            acceptor_half TEXT NOT NULL,
            proposer_confirmed INTEGER DEFAULT 0,
            acceptor_confirmed INTEGER DEFAULT 0,
            finalized INTEGER DEFAULT 0,
            FOREIGN KEY(trade_id) REFERENCES trade(id)
        );

        CREATE TABLE ongoing_transaction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            code TEXT NOT NULL,
            started_at TEXT,
            FOREIGN KEY(transaction_id) REFERENCES "transaction"  -- << quotes here too
        );
        ''')

    conn.commit()
    conn.close()

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user (username, email, password, role) VALUES (?, ?, ?, ?)',
                   (data['username'], data['email'], data['password'], data['role']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'User registered successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user WHERE username = ? AND password = ?',
                   (data['username'], data['password']))
    user = cursor.fetchone()
    conn.close()
    if user:
        return jsonify({'message': 'Login successful', 'user_id': user['id'], 'role': user['role']})
    else:
        return jsonify({'message': 'Invalid credentials'}), 401

@app.route('/items', methods=['GET'])
def list_items():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT item.*, user.username AS owner_username
        FROM item
        JOIN user ON item.owner_id = user.id
        WHERE item.available = 1
    ''')
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(items)


@app.route('/my_items/<int:user_id>', methods=['GET'])
def get_my_items(user_id):
    conn = get_db()
    cursor = conn.cursor()

    # Step 1: Get partner IDs
    cursor.execute('SELECT partner_id FROM partnership WHERE user_id = ?', (user_id,))
    partners = [row['partner_id'] for row in cursor.fetchall()]
    all_ids = partners + [user_id]

    # Step 2: Get items owned by user or partners
    placeholders = ','.join(['?'] * len(all_ids))
    cursor.execute(f'''
        SELECT item.*, user.username as owner_username FROM item
        JOIN user ON item.owner_id = user.id
        WHERE item.available = 1 AND item.owner_id IN ({placeholders})
    ''', all_ids)

    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(items)

@app.route('/add_item', methods=['POST'])
def add_item():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO item (owner_id, name, description, category, condition, estimated_value)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (data['owner_id'], data['name'], data.get('description', ''), data.get('category', ''),
                    data.get('condition', ''), data.get('estimated_value', 0.0)))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Item added successfully'}), 201

@app.route('/propose_trade', methods=['POST'])
def propose_trade():
    data = request.get_json()
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()

    # Step 1: Insert into Trade
    cursor.execute('''INSERT INTO trade (proposer_id, offered_item_id, requested_item_id, created_at, updated_at)
                      VALUES (?, ?, ?, ?, ?)''',
                   (data['proposer_id'], data['offered_item_id'], data['requested_item_id'], now, now))
    trade_id = cursor.lastrowid

    # Step 2: Create Transaction
    code = generate_code()
    proposer_half = code[:8]
    acceptor_half = code[8:]
    cursor.execute('''INSERT INTO "transaction" (trade_id, code, proposer_half, acceptor_half)
                      VALUES (?, ?, ?, ?)''', (trade_id, code, proposer_half, acceptor_half))
    transaction_id = cursor.lastrowid

    # Step 3: Insert into Ongoing Transaction
    cursor.execute('INSERT INTO ongoing_transaction (transaction_id, code, started_at) VALUES (?, ?, ?)',
                   (transaction_id, code, now))

    conn.commit()
    conn.close()

    # Step 4: Return acceptor_half to frontend
    return jsonify({
        'message': 'Trade proposal sent!',
        'acceptor_half': acceptor_half
    }), 201


@app.route('/create_partnership', methods=['POST'])
def create_partnership():
    data = request.get_json()
    user_id = data['user_id']
    partner_username = data['partner_username']

    conn = get_db()
    cursor = conn.cursor()

    # Find the partner by username
    cursor.execute('SELECT id FROM user WHERE username = ?', (partner_username,))
    partner = cursor.fetchone()

    if not partner:
        conn.close()
        return jsonify({'message': 'Partner username not found'}), 404

    partner_id = partner['id']

    # Insert partnership (both ways if needed)
    cursor.execute('INSERT INTO partnership (user_id, partner_id) VALUES (?, ?)', (user_id, partner_id))
    conn.commit()
    conn.close()

    return jsonify({'message': f'Partnered with {partner_username} successfully!'})


@app.route('/get_partners/<int:user_id>', methods=['GET'])
def get_partners(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT partner_id FROM partnership WHERE user_id = ?', (user_id,))
    partners = [row['partner_id'] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'partners': partners})

@app.route('/add_partner', methods=['POST'])
def add_partner():
    data = request.get_json()
    user_id = data['user_id']
    partner_username = data['partner_username']

    conn = get_db()
    cursor = conn.cursor()

    # Step 1: Find partner's id using username
    cursor.execute('SELECT id FROM user WHERE username = ?', (partner_username,))
    partner = cursor.fetchone()

    if not partner:
        conn.close()
        return jsonify({'message': 'Partner username not found.'}), 404

    partner_id = partner['id']

    # Step 2: Check if partnership already exists
    cursor.execute('SELECT * FROM partnership WHERE user_id = ? AND partner_id = ?', (user_id, partner_id))
    exists = cursor.fetchone()

    if exists:
        conn.close()
        return jsonify({'message': 'Already partnered.'})

    # Step 3: Insert both directions (user -> partner and partner -> user)
    cursor.execute('INSERT INTO partnership (user_id, partner_id) VALUES (?, ?)', (user_id, partner_id))
    cursor.execute('INSERT INTO partnership (user_id, partner_id) VALUES (?, ?)', (partner_id, user_id))

    conn.commit()
    conn.close()

    return jsonify({'message': f'Partnership created successfully with {partner_username}!'}), 201


@app.route('/trades', methods=['GET'])
def list_trades():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM trade')
    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(trades)

@app.route('/respond_trade/<int:trade_id>', methods=['POST'])
def respond_trade(trade_id):
    data = request.get_json()
    status = data['status']
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE trade SET status = ?, updated_at = ? WHERE id = ?', (status, now, trade_id))
    conn.commit()

    if status == 'accepted':
        # Create transaction record
        code = generate_code()
        proposer_half = code[:8]
        acceptor_half = code[8:]
        cursor.execute('INSERT INTO "transaction" (trade_id, code, proposer_half, acceptor_half) VALUES (?, ?, ?, ?)',
                       (trade_id, code, proposer_half, acceptor_half))
        conn.commit()

    conn.close()
    return jsonify({'message': f'Trade {status} successfully'})


@app.route('/ongoing_transaction', methods=['POST'])
def create_ongoing_transaction():
    data = request.get_json()
    transaction_id = data['transaction_id']
    now = datetime.now().isoformat()

    conn = get_db()
    cursor = conn.cursor()

    # Step 1: Check if transaction exists and get its code
    cursor.execute('SELECT code FROM transaction WHERE id = ?', (transaction_id,))
    transaction = cursor.fetchone()

    if not transaction:
        conn.close()
        return jsonify({'message': 'Transaction not found'}), 404

    code = transaction['code']

    # Step 2: Insert into ongoing_transaction table
    cursor.execute('INSERT INTO ongoing_transaction (transaction_id, code, started_at) VALUES (?, ?, ?)',
                   (transaction_id, code, now))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Ongoing transaction started', 'transaction_id': transaction_id}), 201

@app.route('/ongoing_transaction_code/<int:transaction_id>', methods=['GET'])
def get_ongoing_transaction_code(transaction_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT code FROM ongoing_transaction WHERE transaction_id = ?', (transaction_id,))
    ongoing = cursor.fetchone()
    
    conn.close()

    if ongoing:
        return jsonify({'transaction_id': transaction_id, 'code': ongoing['code']})
    else:
        return jsonify({'message': 'Ongoing transaction not found'}), 404


@app.route('/submit_code', methods=['POST'])
def submit_code():
    data = request.get_json()
    trade_id = data['trade_id']
    half_code = data['half_code']

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM "transaction" WHERE trade_id = ?', (trade_id,))
    transaction = cursor.fetchone()

    if not transaction:
        conn.close()
        return jsonify({'message': 'Transaction not found'}), 404

    proposer_half = transaction['proposer_half']
    acceptor_half = transaction['acceptor_half']

    if half_code == proposer_half:
        # Correct proposer half entered
        cursor.execute('UPDATE "transaction" SET proposer_confirmed = 1 WHERE trade_id = ?', (trade_id,))
        conn.commit()
        other_half = acceptor_half
        conn.close()
        return jsonify({'message': 'Proposer half-code accepted.', 'other_half': other_half})

    elif half_code == acceptor_half:
        # Correct acceptor half entered
        cursor.execute('UPDATE "transaction" SET acceptor_confirmed = 1 WHERE trade_id = ?', (trade_id,))
        conn.commit()
        other_half = proposer_half
        conn.close()
        return jsonify({'message': 'Acceptor half-code accepted.', 'other_half': other_half})

    else:
        conn.close()
        return jsonify({'message': 'Invalid code entered.'}), 400

@app.route('/get_transaction/<int:trade_id>', methods=['GET'])
def get_transaction(trade_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT proposer_confirmed, acceptor_confirmed, finalized FROM "transaction" WHERE trade_id = ?', (trade_id,))
    transaction = cursor.fetchone()
    conn.close()

    if transaction:
        return jsonify(dict(transaction))
    else:
        return jsonify({'message': 'Transaction not found'}), 404

@app.route('/finalize_trade/<int:trade_id>', methods=['POST'])
def finalize_trade(trade_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT proposer_confirmed, acceptor_confirmed FROM "transaction" WHERE trade_id = ?', (trade_id,))
    transaction = cursor.fetchone()

    if not transaction:
        conn.close()
        return jsonify({'message': 'Transaction not found.'}), 404

    if transaction['proposer_confirmed'] and transaction['acceptor_confirmed']:
        # Finalize transaction
        cursor.execute('UPDATE "transaction" SET finalized = 1 WHERE trade_id = ?', (trade_id,))
        conn.commit()

        # Delete trade
        cursor.execute('DELETE FROM trade WHERE id = ?', (trade_id,))
        conn.commit()
        

        conn.close()
        return jsonify({'message': 'Trade finalized and deleted successfully.'})
    else:
        conn.close()
        return jsonify({'message': 'Both sides have not confirmed yet.'}), 400


@app.route('/mark_unavailable', methods=['POST'])
def mark_unavailable():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    for item_id in data['item_ids']:
        cursor.execute('UPDATE item SET available = 0 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Items marked unavailable'})

@app.route('/delete_trade/<int:trade_id>', methods=['DELETE'])
def delete_trade(trade_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM trade WHERE id = ?', (trade_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Trade deleted'})

#profile routes

@app.route('/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role FROM user WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return jsonify(dict(user))
    else:
        return jsonify({'message': 'User not found'}), 404

@app.route('/profile/<int:user_id>', methods=['PUT'])
def update_profile(user_id):
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE user
        SET username = ?, email = ?
        WHERE id = ?
    ''', (data['username'], data['email'], user_id))

    conn.commit()
    conn.close()

    return jsonify({'message': 'Profile updated successfully!'})

#admin routes

@app.route('/admin_login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data['username']
    password = data['password']

    # Hardcoded secret admin credentials
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'admin123'

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return jsonify({'message': 'Admin login successful!'}), 200
    else:
        return jsonify({'message': 'Invalid admin credentials.'}), 401

@app.route('/admin/users', methods=['GET'])
def admin_get_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email FROM user')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/admin/items', methods=['GET'])
def admin_get_items():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT item.id, item.name, item.description, item.category, item.condition, item.estimated_value, user.username AS owner_username
        FROM item
        JOIN user ON item.owner_id = user.id
    ''')
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(items)

@app.route('/admin/partnerships', methods=['GET'])
def admin_get_partnerships():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, u1.username as user, u2.username as partner
        FROM partnership p
        JOIN user u1 ON p.user_id = u1.id
        JOIN user u2 ON p.partner_id = u2.id
    ''')
    partnerships = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(partnerships)

@app.route('/admin/finalized_trades', methods=['GET'])
def admin_get_finalized_trades():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.id AS trade_id, tr.code, u.username AS proposer_username
        FROM trade t
        JOIN "transaction" tr ON t.id = tr.trade_id
        JOIN user u ON t.proposer_id = u.id
        WHERE tr.finalized = 1
    ''')
    finalized = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(finalized)

@app.route('/admin/delete_user/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'User deleted successfully.'})

@app.route('/admin/delete_item/<int:item_id>', methods=['DELETE'])
def admin_delete_item(item_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM item WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Item deleted successfully.'})

@app.route('/admin/delete_partnership/<int:partnership_id>', methods=['DELETE'])
def admin_delete_partnership(partnership_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM partnership WHERE id = ?', (partnership_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Partnership deleted successfully.'})

@app.route("/")
def home():
    return render_template("index.html")
    
if __name__ == '__main__':
    init_db()

    app.run(debug=True)


