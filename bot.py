import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

quizzes = {} 
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Quiz Bot!\n\n"
        "✨ **Commands:**\n"
        "/list - Saare available quizzes dekhne ke liye\n"
        "/play [Quiz_ID] - Quiz khelne ke liye\n\n"
        "📂 **File se Quiz kaise banayein:**\n"
        "Apni text (.txt) file chat mein bhejhein aur caption mein likhein:\n"
        "`/import Quiz_Ka_Naam`"
    )

async def list_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quizzes:
        await update.message.reply_text("📂 Filhal koi quiz available nahi hai. Kripya pehle koi `.txt` file `/import [Naam]` ke sath bhej kar quiz banayein!")
        return
    
    text = "📋 **Available Quizzes:**\n\n"
    for q_id, q_data in quizzes.items():
        text += f"🆔 **Quiz ID:** `{q_id}`\n📌 **Title:** {q_data['title']}\n❓ **Total Questions:** {len(q_data['questions'])}\n------------------\n"
    text += "\nKisi quiz ko khelne ke liye `/play [Quiz_ID]` likhein"
    await update.message.reply_text(text)

async def play_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Kripya Quiz ID dein. Jaise: `/play 1`")
        return
    
    quiz_id = args[0]
    if quiz_id not in quizzes:
        await update.message.reply_text("❌ Ye Quiz ID galat hai. `/list` check karein.")
        return
    
    quiz = quizzes[quiz_id]
    user_id = update.effective_user.id
    
    context.user_data[f"playing_{user_id}"] = {
        "quiz_id": quiz_id,
        "q_index": 0,
        "score": 0
    }
    
    await update.message.reply_text(f"🚀 Quiz Start: **{quiz['title']}**\n\nPehla Question:")
    await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    play_data = context.user_data.get(f"playing_{user_id}")
    if not play_data:
        return
    
    quiz = quizzes[play_data["quiz_id"]]
    q_index = play_data["q_index"]
    
    if q_index >= len(quiz["questions"]):
        score = play_data["score"]
        total = len(quiz["questions"])
        await update.message.reply_text(
            f"🎉 **Quiz Complete!**\n\n"
            f"Aapka Score: **{score} / {total}**"
        )
        del context.user_data[f"playing_{user_id}"]
        return
    
    q_data = quiz["questions"][q_index]
    options_text = "\n".join([f"{opt}" for opt in q_data["options"]])
    
    await update.message.reply_text(
        f"❓ **Question {q_index + 1} of {len(quiz['questions'])}:**\n"
        f"{q_data['question']}\n\n"
        f"{options_text}\n\n"
        f"*(Sahi option ka letter reply karein, jaise: a, b, c, ya d)*"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    caption = update.message.caption
    
    if not caption or not caption.startswith("/import"):
        await update.message.reply_text("⚠️ Kripya file bhejte waqt caption mein `/import Quiz_Naam` zaroor likhein.")
        return

    quiz_title = caption.replace("/import", "").strip()
    if not quiz_title:
        quiz_title = "Uploaded Quiz"

    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    file_content = file_bytes.decode("utf-8")

    questions = []
    blocks = file_content.split("Q")
    
    for block in blocks:
        if not block.strip():
            continue
        try:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            q_text = lines[0].split(". ", 1)[1] if ". " in lines[0] else lines[0]
            
            options = []
            correct_ans = ""
            
            for line in lines[1:]:
                if any(line.startswith(prefix) for prefix in ["(a)", "(b)", "(c)", "(d)", "a)", "b)", "c)", "d)"]):
                    if "✅" in line:
                        correct_ans = line.replace("(", "").replace(")", "")[0].lower()
                    options.append(line.replace("✅", "").strip())
                elif line.startswith("Ex:"):
                    break
                    
            if q_text and options and correct_ans:
                questions.append({
                    "question": q_text,
                    "options": options,
                    "answer": correct_ans
                })
        except Exception as e:
            continue

    if not questions:
        await update.message.reply_text("❌ File read nahi ho saki. Kripya sahi format wali .txt file bhejein.")
        return

    quiz_id = str(len(quizzes) + 1)
    quizzes[quiz_id] = {
        "title": quiz_title,
        "creator_name": update.effective_user.first_name,
        "questions": questions
    }

    await update.message.reply_text(
        f"✅ **Quiz Successfully Created!**\n\n"
        f"📌 **Title:** {quiz_title}\n"
        f"🔢 **Total Questions:** {len(questions)}\n"
        f"🆔 **Quiz ID:** `{quiz_id}`\n\n"
        f"Khelne ke liye bhejiye: `/play {quiz_id}`"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    play_key = f"playing_{user_id}"
    if play_key in context.user_data:
        play_data = context.user_data[play_key]
        quiz = quizzes[play_data["quiz_id"]]
        q_data = quiz["questions"][play_data["q_index"]]
        
        user_ans = text.replace("(", "").replace(")", "").strip().lower()
        
        if user_ans == q_data["answer"] or user_ans in q_data["answer"]:
            play_data["score"] += 1
            await update.message.reply_text("✅ Sahi jawab!")
        else:
            await update.message.reply_text(f"❌ Galat jawab! Sahi option tha: *({q_data['answer'].upper()})*")
            
        play_data["q_index"] += 1
        await send_question(update, context)
        return

if __name__ == '__main__':
    TOKEN = "9269979361:AAGk8w47dP8oGijvRVuRDNvnCLMXlWA-HuU"
    
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_quizzes))
    app.add_handler(CommandHandler("play", play_quiz))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot started successfully...")
    app.run_polling()
