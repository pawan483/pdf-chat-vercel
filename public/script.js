const uploadBtn = document.getElementById("uploadBtn");
const sendBtn = document.getElementById("sendBtn");
const pdfFile = document.getElementById("pdfFile");
const uploadStatus = document.getElementById("uploadStatus");
const messageInput = document.getElementById("messageInput");
const chatMessages = document.getElementById("chatMessages");

function addMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "YOU" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  wrapper.appendChild(avatar);
  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

uploadBtn.addEventListener("click", async () => {
  const file = pdfFile.files[0];

  if (!file) {
    uploadStatus.textContent = "Please select a PDF file first.";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  uploadStatus.textContent = "Processing PDF...";

  try {
    const response = await fetch("/api/upload-pdf", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      uploadStatus.textContent = data.detail || "Upload failed.";
      return;
    }

    uploadStatus.textContent = data.message || "PDF processed successfully.";
    addMessage("bot", "Your PDF is ready. Ask me anything about it.");
  } catch (error) {
    uploadStatus.textContent = "Something went wrong while uploading the PDF.";
  }
});

async function sendMessage() {
  const message = messageInput.value.trim();

  if (!message) return;

  addMessage("user", message);
  messageInput.value = "";
  addMessage("bot", "Thinking...");

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ message })
    });

    const data = await response.json();
    chatMessages.removeChild(chatMessages.lastChild);

    if (!response.ok) {
      addMessage("bot", data.detail || "Something went wrong.");
      return;
    }

    let answer = data.answer || "No answer returned.";
    if (data.sources && data.sources.length) {
      answer += `\n\nSources: Page ${data.sources.join(", ")}`;
    }

    addMessage("bot", answer);
  } catch (error) {
    chatMessages.removeChild(chatMessages.lastChild);
    addMessage("bot", "Server error. Please try again.");
  }
}

sendBtn.addEventListener("click", sendMessage);

messageInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") {
    sendMessage();
  }
});
