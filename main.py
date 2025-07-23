from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from typing import List,Dict
import requests
import base64
import pymongo
import pandas as pd
from io import BytesIO
from fastapi.encoders import jsonable_encoder
import google.generativeai as genai
from dotenv import load_dotenv
import os, json, re
app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mycli = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = mycli["codingEditor"]
mycol_email = mydb["Emails"]
mycol_que = mydb["quesions"]

# dem = pymongo.MongoClient("mongodb+srv://yagneshreddysomavarapu:Y@gneshreddy#2003@cluster0.pjupkqo.mongodb.net/")
# dem_db = dem['YR']
# dem_col = dem_db['Email']

class EmailPassword(BaseModel):
    email: str
    password: str
@app.post("/app/email")
async def email(data: EmailPassword):
    # global email 
    email = data.email 
    password = data.password
    if (data.password.isdigit()):
        password = int(data.password)
        check = mycol_email.find_one({"email":email,"password":password,'Attempt':'Not Attempt'})
        check_2 = mycol_email.find_one({"email":email,"password":password})
        if check:
           return "sucss"
        elif check_2:
           return "User Already Write this exam."
        else:
           return "User Email/Password incorrect"
    else:
           return "User Email/Password incorrect"


class QueNos(BaseModel):
    queNo : str

@app.post("/app/questions")
async def quesions(data : QueNos):
    # print("quesion number >> 2")
    que = mycol_que.find_one({"questionNo":data.queNo})
    first_input = que["inputs"][0]["input"] if que.get("inputs") else ""
    li = [{"a": i} for i in range(1, 11)]
    fetch_marks = mycol_email.find_one({"email": "yagneshreddysomavarapu@gmail.com"}, {'_id': 0})
    QAtt = "NotYet"
    try:
        qmarks = fetch_marks['QMarks'][0]
    except:
        qmarks = []
    return {
        "title": que.get("title"),
        "question": que.get("description"),
        "first_input": first_input,
        "testcases": li,
        "QAtt" : qmarks
    }
class users(BaseModel):
    user : str
@app.post("/app/user")
async def user(data:users):

    check = mycol_email.find_one({"email":data.user,'Attempt':'Not Attempt'})
    NoOfQue = list(mycol_que.find({},{"_id":0}))
    LastQueNoobj =  list(mycol_que.find({}, {'_id': 0}).sort('_id', -1).limit(1))
    LastQueNo = LastQueNoobj[0]['questionNo']
    if NoOfQue and check:
       return {"TotalQue":NoOfQue,"lastQuesionNo":LastQueNo}
    else:
        return "err"
# Judge0 API details
JUDGE0_URL = "https://judge0-ce.p.rapidapi.com/submissions"
HEADERS = {
    "X-RapidAPI-Key": "640db5e88bmsh0e7bf6495c90995p1cad09jsn5cec7c140fdf",
    "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
    "Content-Type": "application/json"
}

url = "http://localhost:2000/api/v2/execute"


# Request schema
class CodeData(BaseModel):
    code: str
    input: str = ""
    language_id: int

@app.post("/app/get_data")
async def get_data(data: CodeData):
    payload = {
        "language_id": data.language_id,
        "source_code": data.code,
        "stdin": data.input
    }

    response = requests.post(
        JUDGE0_URL + "?base64_encoded=false&wait=true",
        headers=HEADERS,
        json=payload
    )
    
    result = response.json()
    output = result.get("stdout") or result.get("stderr") or result.get("compile_output") or "No output or execution failed."
    return {"output": output}

class TestData(BaseModel):
      code: str
      language_id: int
      queNo:str
      user:str
@app.post("/app/subinput")
def subinput(data : TestData):
    code = data.code
    question = mycol_que.find_one({"questionNo": data.queNo})
    results = []
    count = 0
    db_marks =  mycol_email.find_one({"email":data.user},{"_id":0})
    # print(">>>>>>>>>>marks",data.user,">>>>>>",user_marks)
    que_marks = db_marks['marks']
    for case in question["inputs"]:
        count += 1
        # try:
        #     _ = list(map(int, case["input"].split()))
        # except ValueError:
        #     return {"error": f"Invalid input format in test case {case['test']}: {case['input']}"}
        payload = {
           "language_id": data.language_id,
           "source_code": code,
           "stdin": case["input"]
        } 

# Send to Judge0
        response = requests.post(
            JUDGE0_URL + "?base64_encoded=false&wait=true",
            headers=HEADERS,
            json=payload
        )
        # resp_data = response.json()
        result = response.json()
    # Decode outputs
      
        output = result.get("stdout", "").strip() if result.get("stdout") else ""
        passed = output == case["output"]
        if passed:
            que_marks += case["marks"]
        results.append({
          "input": case["input"],
          "stdout": output,
          "expetedout":case["output"],
          "passed": passed,
          "test":count
         })
    fetch_marks = mycol_email.find_one({"email":data.user},{'_id':0})
    que_marks_list = fetch_marks.get('QMarks',[])
    if data.queNo in fetch_marks['QMarks'][0].keys():
        if fetch_marks['QMarks'][0][data.queNo] < que_marks:
            que_marks_list[0][data.queNo]=que_marks
            mycol_email.update_one({"email":data.user},{'$set':{"QMarks":que_marks_list}})
    else:
        que_marks_list[0][data.queNo]=que_marks
        mycol_email.update_one({"email":data.user},{'$set':{"QMarks":que_marks_list}})
    return results

@app.post("/app/admin")
async def admin(file: UploadFile = File(...)):
    # Read the uploaded Excel file
    contents = await file.read()
    excel_data = BytesIO(contents)
    # Convert bytes to pandas DataFrame
    df = pd.read_csv(excel_data)
    df["marks"] = 0
    df["Attempt"] = "Not Attempt"
    df["QMarks"] =  [[{}] for _ in range(len(df))]
    Excel_data = df.to_dict(orient='records')
    
    # print(dff)
    Mongo_data = mycol_email.find({},{"_id":0})
    if Mongo_data:
        Mongo_list = [rec["email"] for rec in Mongo_data]
        result = 0
        duplicates = 0
        for data in Excel_data:
            if data["email"] not in Mongo_list:
                mycol_email.insert_one(data)
                result += 1
            else:
                duplicates += 1
    else:
        duplicates = 0
        mycol_email.insert_many(Excel_data)
        result = len(Excel_data)
    total = len(list(mycol_email.find({},{"_id":0})))
    return {"AddData":result,"TotalData":total,"Duplicates":duplicates}

@app.get("/app/dele")
def dele():
    mycol_email.delete_many({})
    return "delete sucess"
@app.get('/app/datashow')
def datashow():
    data = mycol_email.find({},{"_id":0})
    result = []
    for item in data:
        result.append(item)
    return result
class names(BaseModel):
    name :str
@app.post('/app/search')
def search(data:names):
    print(data.name)
    data = mycol_email.find({ "name": { "$regex": data.name, "$options": "i" } },{'_id':0})
    result = []
    for item in data:
        result.append(item)
    return result
class sub(BaseModel):
    user:str
@app.post('/app/submit')
def submit(data:sub):
    # print(data.user)
    total_marks = 0
    mongo_user_data = mycol_email.find_one({'email':data.user},{'_id':0})
    user_marks = mongo_user_data.get('QMarks',[])
    for _,v in user_marks[0].items():
        total_marks += v
    mycol_email.update_one({'email':data.user},{'$set':{'marks':total_marks,'Attempt':'Attempted'}})
    return total_marks

@app.post('/app/uploadQuestions')
async def uploadQuesion(file:UploadFile = File(...)):
    print("submit data ....................")
    contents = await file.read()
    excel_data = BytesIO(contents)
    # Convert bytes to pandas DataFrame
    df = pd.read_csv(excel_data)
    print(df)
    data = df.to_dict(orient="records")
    mycol_que.insert_many(data)
    return {"data": data}

@app.get('/app/new')
def getQues():
    que = mycol_que.find({},{'_id':0})
    result = []
    for i in que:
        result.append(i)
    return result

class QNo(BaseModel):
    Qno: str
@app.post('/app/QueDel')
def DelQue(data:QNo):
    que = list(mycol_que.find({}, {'_id': 0}).sort('questionNo', -1).limit(1))
    if not que:
        return {'status': 'no questions available'}

    CurrentQueNo = que[0]['questionNo']

    # Delete the question
    mycol_que.delete_one({'questionNo': data.Qno})

    if CurrentQueNo == data.Qno:
        return {'status': 'success'}
    else:
        for i in range(int(data.Qno), int(CurrentQueNo)):
            mycol_que.update_one(
                {'questionNo': str(i + 1)},
                {"$set": {'questionNo': str(i)}},
                upsert=False
            )
        return {'status': 'success'}

class QuesionType(BaseModel):
    Qname: str
@app.post('/app/Ai')
def showQue(data:QuesionType):

    que = list(mycol_que.find({},{'_id':0}).sort({'_id': -1}).limit(1))

    Quesion_data =f"""I have a coding compiler for a coding quiz. This is the format of JSON data: {que[0]}.  
This is my last question in the compiler — read this and give me exactly in this format.  

Include the following:
- `questionNo`
- `title` (you can improve the title based on the question content)
- `description`: This must be a well-formatted string including input format, output format, constraints, explanation, and an example — just like how it is written on LeetCode or HackerRank.  
  (Do **not** create separate keys for input/output/constraints/explanation — write them all inside the `description` as plain text.)

For test cases:
- There should be exactly 10 test cases.
- Each test case must contain `test`, `input`, `output`, and `marks`.
- Total marks are 100, so each test case should get **10 marks**.
- Keep all key names and format **exactly the same** — do not add any new keys or change any names.

The question title is: `{data.Qname}` — if needed, improve it slightly to make it clear and relevant.

Only return **pure JSON data** — nothing else. No text, no explanation. I want to insert it directly into my MongoDB collection.
"""

    
    load_dotenv()
    genai.configure(api_key = os.getenv("API_KEY"))
    model = genai.GenerativeModel("gemini-2.0-flash")
    result = model.start_chat().send_message(Quesion_data).text
    cleaned_result = re.sub(r"```json|```", "", result).strip()
    json_result = json.loads(cleaned_result)
    # print(json_result)

    mycol_que.insert_one(json_result)
    return {"states":"sucess"}