# How to Run the Nifty Trading Application

This application consists of two parts: a **Python FastAPI backend** and a **React + Vite frontend**. You will need to run both concurrently in separate terminal windows for the application to work properly.

---

## Prerequisites
Before you begin, ensure you have the following installed on your system:
- **Python 3.9+**
- **Node.js** (v16 or higher recommended)
- **npm** (Node Package Manager)

---

## 1. Running the Backend (FastAPI)

The backend handles the trading logic, database, market data feeds (Angel One API), and provides the REST API endpoints.

**Step 1: Open a terminal and navigate to the backend folder**
```bash
cd c:\Users\tokes\Desktop\Nifty\Nifty_Trading\backend
```

**Step 2: Activate the virtual environment**
If you haven't activated the virtual environment yet:
*(On Windows)*
```bash
venv\Scripts\activate
```
*(On Mac/Linux)*
```bash
source venv/bin/activate
```

**Step 3: Install Dependencies (if not already installed)**
```bash
pip install -r requirements.txt
```

**Step 4: Ensure Environment Variables are set**
Make sure your `.env` file exists in the `backend` directory containing your Angel One Smart API credentials (`ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET`).

**Step 5: Start the Server**
Run the FastAPI application using Uvicorn:
```bash
uvicorn main:app --reload
```
The backend server will start and typically run on `http://127.0.0.1:8000`. You can view the API documentation at `http://127.0.0.1:8000/docs`.

---

## 2. Running the Frontend (React + Vite)

The frontend provides the User Interface (Dashboards, Trades, Paper Trading, etc.).

**Step 1: Open a NEW separate terminal and navigate to the frontend folder**
```bash
cd c:\Users\tokes\Desktop\Nifty\Nifty_Trading\frontend
```

**Step 2: Install Node Modules (First time only)**
```bash
npm install
```

**Step 3: Start the Development Server**
```bash
npm run dev
```

**Step 4: Access the Application**
Once the Vite server starts, it will provide a local URL (usually `http://localhost:5173`). Open that URL in your web browser to view your trading application.

---

## Summary of Daily Start Routine
1. Terminal 1 $\rightarrow$ `cd backend` $\rightarrow$ `venv\Scripts\activate` $\rightarrow$ `uvicorn main:app --reload`
2. Terminal 2 $\rightarrow$ `cd frontend` $\rightarrow$ `npm run dev`
3. Open browser to `http://localhost:5173`
