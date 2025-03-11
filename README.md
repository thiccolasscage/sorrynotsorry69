## **🚀 Discord Bot - SorryNotSorry**
A fun and interactive Discord bot that tracks swear words, manages a virtual swear jar, and provides moderation tools. Hosted using **Railway.app**.

---

## **📌 Features**
- 🚫 **Swear Jar**: Tracks swears, deducts coins, and warns users.
- 🏆 **Leaderboard**: Displays top offenders.
- 💰 **Virtual Economy**: Users have a balance and can lose coins.
- 🔇 **Auto-Muting**: Mutes users who exceed the warning limit.
- 🛠 **Admin Tools**: Add/remove banned words, reset user stats, and change currency.

---

## **⚡ Commands**
| **Command** | **Description** | **Example** |
|------------|---------------|------------|
| **`/leaderboard`** | Shows the top 5 swearers | `/leaderboard` |
| **`/banned_words`** | Lists all banned words | `/banned_words` |
| **`/addswear <word>`** | Adds a new swear word | `/addswear heck` |
| **`/removeswear <word>`** | Removes a swear word | `/removeswear sorry` |
| **`/balance`** | Shows your remaining coins | `/balance` |
| **`/mute <@user>`** | Manually mute a user | `/mute @Alex` |
| **`/reset_user <@user>`** | Resets a user's stats | `/reset_user @Penny` |
| **`/set_currency <name>`** | Changes currency name | `/set_currency gold` |
| **`/tally <@user>`** | Shows swear count via slash command | `/tally @John` |

---

## **🔧 Setup & Installation**
### **1️⃣ Local Setup**
**📌 Prerequisites**
- Python **3.8+** installed
- `pip` installed

#### **1. Clone Repository**
```sh
git clone https://github.com/your-github-username/sorrynotsorry.git
cd sorrynotsorry
```

#### **2. Create a Virtual Environment**
```sh
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows
```

#### **3. Install Dependencies**
```sh
pip install -r requirements.txt
```

#### **4. Set Up Environment Variables**
Create a `.env` file and add:
```
DISCORD_BOT_TOKEN=your-bot-token-here
```

#### **5. Run the Bot**
```sh
python bot.py
```

---

## **🌍 Hosting on Railway.app**
**1️⃣ Sign Up & Install CLI**
```sh
npm install -g @railway/cli
railway login
```

**2️⃣ Link Project**
```sh
railway init
```

**3️⃣ Add Environment Variables**
```sh
railway env set DISCORD_BOT_TOKEN=your-bot-token
```

**4️⃣ Deploy**
```sh
railway up
```

---

## **🛠 Contributing**
- Feel free to **fork**, submit **pull requests**, or open **issues**.

---

## **📜 License**
This project is **open-source** under the **MIT License**.

---

### **💬 Questions or Support?**
- Open an **issue** on GitHub.
- Join our **Discord server** (if applicable).
