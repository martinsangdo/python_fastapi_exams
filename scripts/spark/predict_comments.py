import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.feature_extraction.text import CountVectorizer
from datasets import load_dataset

# 1. LOAD DATA FROM PARQUET
dataset = load_dataset("parquet", data_files="ai_training_lake.parquet")
texts = dataset["train"]["review_text"]
ratings = dataset["train"]["rating"]

# 2. CONVERT TEXT & RATINGS TO SIMPLE NUMBERS
# Turn text into a fixed grid of 10 word counts (Bag of Words)
vectorizer = CountVectorizer(max_features=10)
X_data = vectorizer.fit_transform(texts).toarray()

# Convert ratings to 3 target categories: 0 (Negative), 1 (Neutral), 2 (Positive)
y_data = [0 if r <= 2 else (1 if r == 3 else 2) for r in ratings]

# Convert arrays directly into clean PyTorch Tensors
X_tensor = torch.tensor(X_data, dtype=torch.float32)
y_tensor = torch.tensor(y_data, dtype=torch.long)

# Package into a standard PyTorch DataLoader (Batch size = 2)
loader = DataLoader(TensorDataset(X_tensor, y_tensor), batch_size=2, shuffle=True)

# 3. DEFINE A SIMPLE 1-LAYER NEURAL NETWORK
# It takes 10 word inputs and maps them directly to 3 sentiment outputs
model = nn.Linear(in_features=10, out_features=3)

criterion = nn.CrossEntropyLoss()                 # Grading system
optimizer = torch.optim.Adam(model.parameters(), lr=0.1) # Weight adjuster

print("🚀 Starting Simple PyTorch Training Loop:\n")

# 4. THE CORE 5-STEP PYTORCH LOOP
for epoch in range(5):
    for batch_x, batch_y in loader:
        # Step 1: Clear out old calculations
        optimizer.zero_grad()
        
        # Step 2: Guess the sentiment (Forward Pass)
        predictions = model(batch_x)
        
        # Step 3: Calculate the mathematical error (Loss)
        loss = criterion(predictions, batch_y)
        
        # Step 4: Calculate adjustments needed (Backward Pass)
        loss.backward()
        
        # Step 5: Tweak the network weights (Optimize)
        optimizer.step()
        
    print(f"Epoch {epoch+1} Complete | Loss: {loss.item():.4f}")

print("\n✅ Training finished successfully!")

#test
# ----------------------------------------------------
# 5. TEST THE MODEL WITH NEW RAW TEXT (INFERENCE)
# ----------------------------------------------------
print("\n🔮 Testing the trained model on new text...")

# Define our human-readable class names matching our target codes (0, 1, 2)
class_names = {0: "Negative 🔴", 1: "Neutral 🟡", 2: "Positive 🟢"}

# Simulate a brand new customer comment scraping from social media (No rating exists!)
new_comment = ["This product is broken and terrible!"]  # Example raw text input

# Step 1: Transform the text into the exact same 10-word number grid format
new_x_data = vectorizer.transform(new_comment).toarray()
new_x_tensor = torch.tensor(new_x_data, dtype=torch.float32)

# Step 2: Turn off gradient calculations (saves memory and speeds up prediction)
model.eval() 
with torch.no_grad():
    # Step 3: Feed the text tensor into the model to get raw confidence scores (logits)
    raw_outputs = model(new_x_tensor)
    
    # Step 4: Find the index of the highest score (0, 1, or 2)
    _, predicted_index = torch.max(raw_outputs, dim=1)
    predicted_class_id = predicted_index.item()

# Step 5: Print out the final prediction
print(f"\nIncoming Comment: \"{new_comment[0]}\"")
print(f"AI Model Prediction: {class_names[predicted_class_id]}")

