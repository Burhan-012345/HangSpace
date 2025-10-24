// Socket.IO configuration and global socket management

class SocketManager {
  constructor() {
    this.socket = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.eventCallbacks = new Map();

    this.initializeSocket();
  }

  initializeSocket() {
    try {
      this.socket = io({
        reconnection: true,
        reconnectionAttempts: this.maxReconnectAttempts,
        reconnectionDelay: this.reconnectDelay,
        reconnectionDelayMax: 5000,
        timeout: 20000,
        autoConnect: true,
      });

      this.setupEventHandlers();
    } catch (error) {
      console.error("Failed to initialize socket:", error);
      this.handleConnectionError(error);
    }
  }

  setupEventHandlers() {
    // Connection events
    this.socket.on("connect", () => {
      console.log("Socket connected successfully");
      this.isConnected = true;
      this.reconnectAttempts = 0;
      this.emit("connection_established");
      this.updateConnectionStatus("connected");
    });

    this.socket.on("disconnect", (reason) => {
      console.log("Socket disconnected:", reason);
      this.isConnected = false;
      this.updateConnectionStatus("disconnected");

      if (reason === "io server disconnect") {
        // Server intentionally disconnected, may need re-authentication
        this.handleServerDisconnect();
      }
    });

    this.socket.on("connect_error", (error) => {
      console.error("Socket connection error:", error);
      this.isConnected = false;
      this.reconnectAttempts++;
      this.updateConnectionStatus("error");
      this.handleConnectionError(error);
    });

    this.socket.on("reconnect", (attemptNumber) => {
      console.log(`Socket reconnected after ${attemptNumber} attempts`);
      this.isConnected = true;
      this.updateConnectionStatus("reconnected");
    });

    this.socket.on("reconnect_attempt", (attemptNumber) => {
      console.log(`Reconnection attempt ${attemptNumber}`);
      this.updateConnectionStatus("reconnecting");
    });

    this.socket.on("reconnect_failed", () => {
      console.error("Failed to reconnect after maximum attempts");
      this.isConnected = false;
      this.updateConnectionStatus("failed");
      this.handleReconnectFailed();
    });

    // Authentication events
    this.socket.on("unauthorized", (error) => {
      console.error("Socket authentication failed:", error);
      this.handleAuthenticationError(error);
    });

    this.socket.on("authenticated", () => {
      console.log("Socket authenticated successfully");
      this.emit("authenticated");
    });

    // Custom application events
    this.setupApplicationEvents();
  }

  setupApplicationEvents() {
    // User presence events
    this.socket.on("user_online", (data) => {
      this.emit("user_online", data);
      this.updateUserPresence(data.user_id, "online");
    });

    this.socket.on("user_offline", (data) => {
      this.emit("user_offline", data);
      this.updateUserPresence(data.user_id, "offline");
    });

    this.socket.on("user_away", (data) => {
      this.emit("user_away", data);
      this.updateUserPresence(data.user_id, "away");
    });

    // Notification events
    this.socket.on("new_notification", (data) => {
      this.emit("new_notification", data);
      this.showNotification(data);
    });

    this.socket.on("notification_read", (data) => {
      this.emit("notification_read", data);
    });

    // Friend system events
    this.socket.on("friend_request_received", (data) => {
      this.emit("friend_request_received", data);
      this.showFriendRequestNotification(data);
    });

    this.socket.on("friend_request_accepted", (data) => {
      this.emit("friend_request_accepted", data);
      this.showFriendAcceptedNotification(data);
    });

    this.socket.on("friend_removed", (data) => {
      this.emit("friend_removed", data);
    });

    // Chat events (these might be handled by ChatManager instead)
    this.socket.on("chat_created", (data) => {
      this.emit("chat_created", data);
    });

    this.socket.on("chat_updated", (data) => {
      this.emit("chat_updated", data);
    });

    // Message events (handled by ChatManager in chat contexts)
    this.socket.on("new_message", (data) => {
      this.emit("new_message", data);
    });

    this.socket.on("message_edited", (data) => {
      this.emit("message_edited", data);
    });

    this.socket.on("message_deleted", (data) => {
      this.emit("message_deleted", data);
    });

    this.socket.on("typing_start", (data) => {
      this.emit("typing_start", data);
    });

    this.socket.on("typing_stop", (data) => {
      this.emit("typing_stop", data);
    });
  }

  // Public methods
  emit(event, data, callback) {
    if (this.isConnected) {
      this.socket.emit(event, data, callback);
    } else {
      console.warn(`Cannot emit ${event}: Socket not connected`);
      this.queueEvent(event, data, callback);
    }
  }

  on(event, callback) {
    this.socket.on(event, callback);

    // Track callbacks for cleanup
    if (!this.eventCallbacks.has(event)) {
      this.eventCallbacks.set(event, []);
    }
    this.eventCallbacks.get(event).push(callback);
  }

  off(event, callback) {
    this.socket.off(event, callback);

    // Remove from tracked callbacks
    if (this.eventCallbacks.has(event)) {
      const callbacks = this.eventCallbacks.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  joinRoom(roomId) {
    this.emit("join_room", { room_id: roomId });
  }

  leaveRoom(roomId) {
    this.emit("leave_room", { room_id: roomId });
  }

  authenticate(token) {
    this.emit("authenticate", { token: token });
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
    }
  }

  reconnect() {
    if (this.socket) {
      this.socket.connect();
    }
  }

  // Event queuing for when socket is disconnected
  queueEvent(event, data, callback) {
    // In a real implementation, you might want to queue events
    // and send them when the connection is restored
    console.warn(`Event queued: ${event}`, data);

    // For now, we'll just show a notification
    this.showOfflineNotification();
  }

  // Event handling methods
  handleConnectionError(error) {
    this.showNotification(
      "Connection lost. Attempting to reconnect...",
      "warning"
    );

    // Notify any components that might be listening
    this.emit("connection_error", { error: error.message });
  }

  handleServerDisconnect() {
    this.showNotification(
      "Disconnected from server. Please refresh the page.",
      "error"
    );

    // Might need to re-authenticate
    setTimeout(() => {
      if (window.currentUser && window.currentUser.token) {
        this.authenticate(window.currentUser.token);
      }
    }, 2000);
  }

  handleReconnectFailed() {
    this.showNotification(
      "Unable to connect to server. Please check your internet connection.",
      "error"
    );

    // Offer manual reconnect option
    if (confirm("Connection failed. Would you like to try reconnecting?")) {
      this.reconnect();
    }
  }

  handleAuthenticationError(error) {
    console.error("Authentication error:", error);
    this.showNotification(
      "Authentication failed. Please log in again.",
      "error"
    );

    // Redirect to login page
    setTimeout(() => {
      window.location.href = "/login?error=auth_failed";
    }, 2000);
  }

  // UI update methods
  updateConnectionStatus(status) {
    const statusElement = document.getElementById("connectionStatus");
    if (statusElement) {
      statusElement.textContent = this.getStatusText(status);
      statusElement.className = `connection-status status-${status}`;
    }

    // Update any connection indicators in the UI
    this.emit("connection_status_changed", { status: status });
  }

  getStatusText(status) {
    const statusMap = {
      connected: "Connected",
      disconnected: "Disconnected",
      reconnecting: "Reconnecting...",
      reconnected: "Reconnected",
      error: "Connection Error",
      failed: "Connection Failed",
    };
    return statusMap[status] || "Unknown";
  }

  updateUserPresence(userId, status) {
    // Update user presence in friend lists, chat headers, etc.
    const elements = document.querySelectorAll(`[data-user-id="${userId}"]`);
    elements.forEach((element) => {
      const statusIndicator =
        element.querySelector(".presence-indicator") ||
        element.querySelector(".online-indicator");
      if (statusIndicator) {
        statusIndicator.className = `presence-indicator status-${status}`;
      }
    });

    this.emit("user_presence_updated", { user_id: userId, status: status });
  }

  showNotification(message, type = "info") {
    // Create or use a notification system
    if (typeof showNotification === "function") {
      showNotification(message, type);
    } else {
      // Fallback notification
      console.log(`[${type.toUpperCase()}] ${message}`);

      // Simple browser notification
      if (type === "error" && Notification.permission === "granted") {
        new Notification("HangSpace", {
          body: message,
          icon: "/static/images/logo.png",
        });
      }
    }
  }

  showOfflineNotification() {
    this.showNotification(
      "You are currently offline. Some features may not work.",
      "warning"
    );
  }

  showFriendRequestNotification(data) {
    const notification = {
      title: "New Friend Request",
      message: `${data.from_username} sent you a friend request`,
      type: "friend_request",
      data: data,
    };

    this.showNotification(notification.message, "info");

    // Update friend request count
    this.updateFriendRequestCount(1);
  }

  showFriendAcceptedNotification(data) {
    const notification = {
      title: "Friend Request Accepted",
      message: `${data.username} accepted your friend request`,
      type: "friend_accepted",
      data: data,
    };

    this.showNotification(notification.message, "success");
  }

  updateFriendRequestCount(increment = 0) {
    const countElement = document.getElementById("friendRequestCount");
    if (countElement) {
      let currentCount = parseInt(countElement.textContent) || 0;
      currentCount += increment;
      countElement.textContent = currentCount;
      countElement.style.display = currentCount > 0 ? "inline" : "none";
    }
  }

  // Utility methods
  isConnected() {
    return this.isConnected;
  }

  getSocketId() {
    return this.socket?.id;
  }

  // Cleanup
  destroy() {
    if (this.socket) {
      // Remove all tracked event listeners
      for (const [event, callbacks] of this.eventCallbacks) {
        callbacks.forEach((callback) => {
          this.socket.off(event, callback);
        });
      }
      this.eventCallbacks.clear();

      this.socket.disconnect();
    }
  }
}

// Global socket manager instance
let socketManager = null;

// Initialize socket manager when needed
function initializeSocketManager() {
  if (!socketManager) {
    socketManager = new SocketManager();
  }
  return socketManager;
}

// Get the socket manager instance
function getSocketManager() {
  if (!socketManager) {
    return initializeSocketManager();
  }
  return socketManager;
}

// Request notification permission
function requestNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().then((permission) => {
      console.log("Notification permission:", permission);
    });
  }
}

// Export for use in other modules
if (typeof module !== "undefined" && module.exports) {
  module.exports = { SocketManager, initializeSocketManager, getSocketManager };
} else {
  window.SocketManager = SocketManager;
  window.initializeSocketManager = initializeSocketManager;
  window.getSocketManager = getSocketManager;
}

// Initialize when document is ready
document.addEventListener("DOMContentLoaded", function () {
  // Only initialize if we're on a page that needs sockets
  if (document.querySelector("[data-needs-socket]")) {
    initializeSocketManager();
    requestNotificationPermission();
  }
});
