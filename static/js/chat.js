// Chat-specific JavaScript functionality

class ChatManager {
  constructor(chatId, currentUserId) {
    this.chatId = chatId;
    this.currentUserId = currentUserId;
    this.socket = io();
    this.isTyping = false;
    this.typingTimer = null;
    this.typingUsers = new Set();

    this.initializeSocket();
    this.initializeEventListeners();
    this.loadChatHistory();
  }

  initializeSocket() {
    // Connect to socket
    this.socket.on("connect", () => {
      console.log("Connected to chat server");
      this.socket.emit("join_chat", { chat_id: this.chatId });
    });

    // Handle new messages
    this.socket.on("new_message", (data) => {
      this.displayMessage(data);
      this.scrollToBottom();
      this.updateChatList(data);
    });

    // Handle typing indicators
    this.socket.on("user_typing", (data) => {
      this.handleTypingIndicator(data);
    });

    // Handle user presence
    this.socket.on("user_online", (data) => {
      this.updateUserStatus(data.user_id, "online");
    });

    this.socket.on("user_offline", (data) => {
      this.updateUserStatus(data.user_id, "offline");
    });

    // Handle user join/leave
    this.socket.on("user_joined", (data) => {
      this.showSystemMessage(`${data.username} joined the chat`);
    });

    this.socket.on("user_left", (data) => {
      this.showSystemMessage(`${data.username} left the chat`);
    });

    // Handle connection errors
    this.socket.on("connect_error", (error) => {
      console.error("Connection error:", error);
      this.showError("Connection lost. Attempting to reconnect...");
    });

    this.socket.on("reconnect", () => {
      console.log("Reconnected to server");
      this.hideError();
    });
  }

  initializeEventListeners() {
    const messageInput = document.getElementById("messageInput");
    const sendButton = document.getElementById("sendButton");

    // Send message on button click
    sendButton.addEventListener("click", () => {
      this.sendMessage();
    });

    // Send message on Enter key (without Shift)
    messageInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // Handle typing indicators
    messageInput.addEventListener("input", () => {
      this.handleUserTyping();
    });

    // Auto-resize textarea
    messageInput.addEventListener("input", this.autoResizeTextarea);

    // Handle file upload (if implemented)
    this.initializeFileUpload();

    // Handle emoji picker (if implemented)
    this.initializeEmojiPicker();

    // Handle message actions
    this.initializeMessageActions();
  }

  sendMessage() {
    const messageInput = document.getElementById("messageInput");
    const message = messageInput.value.trim();

    if (!message) return;

    // Disable send button temporarily
    const sendButton = document.getElementById("sendButton");
    sendButton.disabled = true;

    // Send message via socket
    this.socket.emit(
      "send_message",
      {
        chat_id: this.chatId,
        message: message,
        type: "text",
      },
      (response) => {
        // Re-enable send button
        sendButton.disabled = false;

        if (response && response.error) {
          this.showError("Failed to send message: " + response.error);
        } else {
          // Clear input and reset typing
          messageInput.value = "";
          this.autoResizeTextarea();
          this.resetTyping();
        }
      }
    );

    // Add optimistic update
    this.addOptimisticMessage(message);
  }

  addOptimisticMessage(message) {
    const tempMessage = {
      _id: "temp-" + Date.now(),
      sender_id: this.currentUserId,
      content: message,
      timestamp: new Date(),
      type: "text",
      status: "sending",
    };

    this.displayMessage(tempMessage, true);
    this.scrollToBottom();
  }

  displayMessage(messageData, isOptimistic = false) {
    const messagesContainer = document.getElementById("messagesContainer");
    const messageDiv = document.createElement("div");

    const isOwnMessage = messageData.sender_id === this.currentUserId;

    // CORRECTED: Proper timestamp handling
    let timestamp;
    if (messageData.timestamp) {
      // If timestamp is provided, use it (could be string or Date object)
      timestamp = new Date(messageData.timestamp);
    } else {
      // If no timestamp, use current time
      timestamp = new Date();
    }

    // Use the enhanced formatMessageTime function
    const messageTime = formatMessageTime(timestamp);

    messageDiv.className = `message ${isOwnMessage ? "own" : "other"} ${
      isOptimistic ? "optimistic" : ""
    }`;
    messageDiv.setAttribute("data-message-id", messageData._id);

    let senderName = "You";
    if (!isOwnMessage) {
      // In a real app, you'd have the sender's name from the message data
      senderName = messageData.sender_username || "Unknown User";
    }

    messageDiv.innerHTML = `
            <div class="message-bubble">
                ${
                  !isOwnMessage
                    ? `
                    <div class="message-sender" id="sender-${messageData.sender_id}">
                        ${senderName}
                    </div>
                `
                    : ""
                }
                <div class="message-content">
                    ${this.formatMessageContent(
                      messageData.content,
                      messageData.type
                    )}
                </div>
                <div class="message-time">
                    ${messageTime}
                    ${
                      isOptimistic
                        ? '<i class="fas fa-clock" style="margin-left: 4px;"></i>'
                        : ""
                    }
                </div>
            </div>
        `;

    // Add message to container with animation
    messagesContainer.appendChild(messageDiv);

    // Animate new message
    messageDiv.style.opacity = "0";
    messageDiv.style.transform = "translateY(10px)";

    setTimeout(() => {
      messageDiv.style.transition = "all 0.3s ease";
      messageDiv.style.opacity = "1";
      messageDiv.style.transform = "translateY(0)";
    }, 10);

    // Remove optimistic indicator when real message arrives
    if (!isOptimistic) {
      const optimisticMessage = document.querySelector(
        `[data-message-id^="temp-"]`
      );
      if (optimisticMessage) {
        optimisticMessage.remove();
      }
    }
  }

  formatMessageContent(content, type) {
    switch (type) {
      case "text":
        // Basic formatting for URLs and line breaks
        return content
          .replace(/\n/g, "<br>")
          .replace(
            /(https?:\/\/[^\s]+)/g,
            '<a href="$1" target="_blank" rel="noopener">$1</a>'
          );
      case "image":
        return `<img src="${content}" alt="Shared image" class="message-image" loading="lazy">`;
      case "file":
        return `<div class="file-message">
                    <i class="fas fa-file"></i>
                    <a href="${content.url}" download="${content.name}">${content.name}</a>
                </div>`;
      default:
        return content;
    }
  }

  handleUserTyping() {
    if (!this.isTyping) {
      this.isTyping = true;
      this.socket.emit("typing", {
        chat_id: this.chatId,
        is_typing: true,
      });
    }

    // Clear existing timer
    clearTimeout(this.typingTimer);

    // Set new timer to reset typing
    this.typingTimer = setTimeout(() => {
      this.isTyping = false;
      this.socket.emit("typing", {
        chat_id: this.chatId,
        is_typing: false,
      });
    }, 1000);
  }

  resetTyping() {
    this.isTyping = false;
    clearTimeout(this.typingTimer);
    this.socket.emit("typing", {
      chat_id: this.chatId,
      is_typing: false,
    });
  }

  handleTypingIndicator(data) {
    const typingIndicator = document.getElementById("typingIndicator");
    const typingText = document.getElementById("typingText");

    if (data.is_typing) {
      this.typingUsers.add(data.username);
    } else {
      this.typingUsers.delete(data.username);
    }

    if (this.typingUsers.size > 0) {
      const users = Array.from(this.typingUsers);
      let text = "";

      if (users.length === 1) {
        text = users[0];
      } else if (users.length === 2) {
        text = `${users[0]} and ${users[1]}`;
      } else {
        text = `${users[0]} and ${users.length - 1} others`;
      }

      typingText.textContent = text;
      typingIndicator.style.display = "block";
    } else {
      typingIndicator.style.display = "none";
    }
  }

  autoResizeTextarea() {
    const textarea = document.getElementById("messageInput");
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
  }

  scrollToBottom() {
    const messagesContainer = document.getElementById("messagesContainer");
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  updateUserStatus(userId, status) {
    // Update user status in the chat header or participant list
    const statusElement = document.getElementById(`user-status-${userId}`);
    if (statusElement) {
      statusElement.textContent = status;
      statusElement.className = `status-badge status-${status}`;
    }

    // Update in message sender names if needed
    const senderElements = document.querySelectorAll(
      `[id^="sender-${userId}"]`
    );
    senderElements.forEach((element) => {
      const badge =
        element.querySelector(".user-status-badge") ||
        document.createElement("span");
      badge.className = `user-status-badge status-${status}`;
      badge.textContent = status;
      if (!element.querySelector(".user-status-badge")) {
        element.appendChild(badge);
      }
    });
  }

  showSystemMessage(message) {
    const messagesContainer = document.getElementById("messagesContainer");
    const systemMessage = document.createElement("div");
    systemMessage.className = "system-message";
    systemMessage.innerHTML = `
            <div class="system-content">
                <i class="fas fa-info-circle"></i>
                ${message}
            </div>
        `;
    messagesContainer.appendChild(systemMessage);
    this.scrollToBottom();
  }

  showError(message) {
    // Remove existing error
    this.hideError();

    const errorDiv = document.createElement("div");
    errorDiv.className = "chat-error";
    errorDiv.innerHTML = `
            <div class="error-content">
                <i class="fas fa-exclamation-triangle"></i>
                <span>${message}</span>
                <button class="error-close" onclick="this.parentElement.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

    document
      .querySelector(".chat-container")
      .insertBefore(errorDiv, document.querySelector(".messages-container"));
  }

  hideError() {
    const existingError = document.querySelector(".chat-error");
    if (existingError) {
      existingError.remove();
    }
  }

  loadChatHistory() {
    // In a real implementation, this would load more messages when scrolling up
    console.log("Loading chat history for:", this.chatId);
  }

  initializeFileUpload() {
    // Implementation for file upload functionality
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.style.display = "none";
    fileInput.multiple = true;
    fileInput.accept = "image/*, .pdf, .doc, .docx, .txt";

    fileInput.addEventListener("change", (e) => {
      const files = e.target.files;
      this.handleFileUpload(files);
    });

    // Add file upload button to UI
    const messageInputContainer = document.querySelector(
      ".message-input-wrapper"
    );
    const fileButton = document.createElement("button");
    fileButton.type = "button";
    fileButton.className = "btn btn-secondary";
    fileButton.innerHTML = '<i class="fas fa-paperclip"></i>';
    fileButton.addEventListener("click", () => fileInput.click());

    messageInputContainer.insertBefore(
      fileButton,
      messageInputContainer.firstChild
    );
  }

  handleFileUpload(files) {
    // Implementation for handling file uploads
    console.log("Files to upload:", files);
    // This would typically involve:
    // 1. Validating file types and sizes
    // 2. Uploading to server
    // 3. Sending message with file reference
  }

  initializeEmojiPicker() {
    // Implementation for emoji picker
    const emojiButton = document.createElement("button");
    emojiButton.type = "button";
    emojiButton.className = "btn btn-secondary";
    emojiButton.innerHTML = '<i class="fas fa-smile"></i>';
    emojiButton.addEventListener("click", this.showEmojiPicker);

    const messageInputWrapper = document.querySelector(
      ".message-input-wrapper"
    );
    messageInputWrapper.insertBefore(
      emojiButton,
      document.getElementById("messageInput")
    );
  }

  showEmojiPicker() {
    // Implementation for showing emoji picker
    console.log("Show emoji picker");
  }

  initializeMessageActions() {
    // Add right-click context menu for messages
    document.addEventListener("contextmenu", (e) => {
      const messageElement = e.target.closest(".message");
      if (messageElement && !messageElement.classList.contains("optimistic")) {
        e.preventDefault();
        this.showMessageContextMenu(e, messageElement);
      }
    });

    // Hide context menu when clicking elsewhere
    document.addEventListener("click", () => {
      this.hideMessageContextMenu();
    });
  }

  showMessageContextMenu(event, messageElement) {
    // Implementation for message context menu (reply, edit, delete, etc.)
    console.log("Show context menu for message:", messageElement);
  }

  hideMessageContextMenu() {
    // Hide any visible context menus
    const existingMenu = document.querySelector(".message-context-menu");
    if (existingMenu) {
      existingMenu.remove();
    }
  }

  updateChatList(messageData) {
    // Update the chat list in the dashboard with the latest message
    if (typeof updateChatInList === "function") {
      updateChatInList(this.chatId, messageData);
    }
  }

  // Cleanup method
  destroy() {
    this.socket.disconnect();
    this.resetTyping();
  }
}

// Initialize chat when DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  const chatId = document.querySelector(".chat-container")?.dataset?.chatId;
  const currentUserId =
    document.querySelector(".chat-container")?.dataset?.currentUserId;

  if (chatId && currentUserId) {
    window.chatManager = new ChatManager(chatId, currentUserId);
  }
});

// ENHANCED Utility functions
function formatMessageTime(timestamp) {
  const now = new Date();
  const messageTime = new Date(timestamp);
  const diffInHours = (now - messageTime) / (1000 * 60 * 60);
  const diffInDays = Math.floor(diffInHours / 24);

  // If message is from today, show time only
  if (diffInDays === 0) {
    return messageTime.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  }

  // If message is from yesterday
  if (diffInDays === 1) {
    return (
      "Yesterday " +
      messageTime.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      })
    );
  }

  // If message is from this week (within 7 days)
  if (diffInDays < 7) {
    const days = [
      "Sunday",
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
    ];
    return (
      days[messageTime.getDay()] +
      " " +
      messageTime.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      })
    );
  }

  // For older messages, show date and time
  return (
    messageTime.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }) +
    " " +
    messageTime.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    })
  );
}

function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Function to update existing message times on page load
function updateExistingMessageTimes() {
  const messageTimes = document.querySelectorAll(".message-time");
  messageTimes.forEach((timeElement) => {
    const messageElement = timeElement.closest(".message");
    const messageId = messageElement.getAttribute("data-message-id");

    // For existing messages, we need to get the original timestamp
    // This would typically come from your server data
    // For now, we'll enhance the format if possible
    const currentText = timeElement.textContent.trim();

    // If it's already in a good format, leave it as is
    // Otherwise, we could try to parse it or leave it unchanged
    if (currentText && currentText.length <= 8 && currentText.includes(":")) {
      // This is likely a time-only format, which is fine
      return;
    }
  });
}

// Initialize time formatting for existing messages when page loads
document.addEventListener("DOMContentLoaded", function () {
  setTimeout(updateExistingMessageTimes, 100);
});
