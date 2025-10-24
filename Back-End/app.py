from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import base64
import logging

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


logging.basicConfig(level=logging.INFO)


JUDGE0_URL = "https://ce.judge0.com"


LANGUAGE_MAP = {
    "Python 3": 71,
    "Node.js (JavaScript)": 63,
    "C++": 54,
    "C": 50,
    "Java": 62,
    "C#": 51,
    "Go": 60,
    "Rust": 73,
    "TypeScript": 74,
    "Plain Text": 43,
}


def decode_base64_output(data):
    """Decodes base64-encoded data, handling None or errors gracefully."""
    if data is None:
        return ""
    try:
        return base64.b64decode(data).decode('utf-8', errors='ignore')
    except (TypeError, ValueError):
        return str(data)


@app.route('/api/submit', methods=['POST'])
def submit_code():
    """
    Step 1: Receives code, sends it to Judge0, and returns the submission token.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400

        code = data.get('code', '')
        language_name = data.get('language', 'python')
        stdin = data.get('stdin', '')

        language_id = LANGUAGE_MAP.get(language_name)
        if not language_id:
            return jsonify({"error": f"Unsupported language: {language_name}"}), 400

        encoded_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')
        encoded_stdin = base64.b64encode(stdin.encode('utf-8')).decode('utf-8')

        url = f"{JUDGE0_URL}/submissions?base64_encoded=true&wait=false"

        payload = {
            "source_code": encoded_code,
            "language_id": language_id,
            "stdin": encoded_stdin,
            "cpu_time_limit": 5,
            "memory_limit": 256000
        }

        headers = {"content-type": "application/json"}

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        token = response.json().get('token')
        app.logger.info(f"Submission successful. Token: {token}")
        return jsonify({"token": token}), 202

    except requests.exceptions.HTTPError as e:
        error_details = e.response.text
        app.logger.error(f"Judge0 API Error: {error_details}")
        return jsonify({"error": "Failed to submit code to compiler service.", "details": error_details}), 502
    except Exception as e:
        app.logger.error(f"Internal Server Error: {e}")
        return jsonify({"error": "An unexpected server error occurred."}), 500


@app.route('/api/status/<string:token>', methods=['GET'])
def get_status(token):
    """
    Step 2: Receives a token and polls Judge0 for the execution result.
    """
    if not token:
        return jsonify({"error": "Token is required"}), 400
        
    try:
        url = f"{JUDGE0_URL}/submissions/{token}?base64_encoded=true&fields=stdout,stderr,compile_output,time,memory,status"
        
        response = requests.get(url)
        response.raise_for_status()

        result = response.json()
        status_id = result.get('status', {}).get('id')
        
        if status_id in [1, 2]:
            return jsonify({"status": {"description": "Pending"}}), 200

        final_result = {
            "status": result.get('status', {}).get('description', 'Unknown Error'),
            "stdout": decode_base64_output(result.get('stdout')),
            "stderr": decode_base64_output(result.get('stderr')),
            "compile_output": decode_base64_output(result.get('compile_output')),
            "time": result.get('time'),
            "memory": result.get('memory'),
        }

        return jsonify(final_result), 200

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return jsonify({"error": "Invalid or expired token."}), 404
        error_details = e.response.text
        app.logger.error(f"Judge0 Polling Error: {error_details}")
        return jsonify({"error": "Failed to retrieve results from compiler service.", "details": error_details}), 502
    except Exception as e:
        app.logger.error(f"Internal Polling Error: {e}")
        return jsonify({"error": "An unexpected server error occurred during polling."}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

