import pymongo
import os

from dotenv import load_dotenv
load_dotenv(override=True)  # Tải biến môi trường từ file .env nếu có

# Chuỗi kết nối tới cả 2 nguồn Database
ATLAS_URI = os.getenv("REMOTE_MONGO_DB")    
LOCAL_URI = os.getenv("LOCAL_MONGO_DB")  # Tải URI từ biến môi trường

def start_sync():
    atlas_client = pymongo.MongoClient(ATLAS_URI)
    local_client = pymongo.MongoClient(LOCAL_URI)
    
    atlas_db = atlas_client["db_certificates"]
    local_db = local_client["db_certificates"]
    
    print("Đang lắng nghe dữ liệu thay đổi từ MongoDB Atlas...")
    
    # Theo dõi mọi thay đổi trên collection 'exams' ở Atlas
    with atlas_db["exams"].watch() as stream:
        for change in stream:
            operation_type = change["operationType"]
            document_id = change["documentKey"]["_id"]
            
            # 1. Nếu có bản ghi MỚI được thêm ở Atlas
            if operation_type == "insert":
                full_document = change["fullDocument"]
                local_db["exams"].insert_one(full_document)
                print(f"[Đồng bộ] Đã thêm mới Exam ID: {document_id}")
                
            # 2. Nếu có bản ghi bị CẬP NHẬT ở Atlas
            elif operation_type == "update":
                updated_fields = change["updateDescription"]["updatedFields"]
                removed_fields = change["updateDescription"]["removedFields"]
                
                update_query = {}
                if updated_fields:
                    update_query["$set"] = updated_fields
                if removed_fields:
                    update_query["$unset"] = {field: 1 for field in removed_fields}
                    
                local_db["exams"].update_one({"_id": document_id}, update_query)
                print(f"[Đồng bộ] Đã cập nhật Exam ID: {document_id}")
                
            # 3. Nếu có bản ghi bị XÓA ở Atlas
            elif operation_type == "delete":
                local_db["exams"].delete_one({"_id": document_id})
                print(f"[Đồng bộ] Đã xóa Exam ID: {document_id}")

if __name__ == "__main__":
    start_sync()