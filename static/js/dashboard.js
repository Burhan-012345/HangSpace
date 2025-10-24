class DashboardManager {
  constructor() {
    this.socket = null;
    this.currentUser = null;
    this.friends = [];
    this.chats = [];
    this.pendingRequests = [];
    this.notifications = [];
    this.unreadNotificationCount = 0;
    this.bellIcons = new Map(); // Map to track bell icons by sender ID
    this.initialize();
  }

  async initialize() {
    console.log("🚀 Initializing Dashboard...");
    await this.loadUserData();
    this.initializeSocket();
    this.initializeEventListeners();
    this.initializeSearch();
    this.initializeNotifications();
    this.createBellIconsContainer();
    this.loadDashboardData();
    console.log("✅ Dashboard initialized successfully");
  }

  async loadUserData() {
    try {
      // Get current user data from the page
      const userElement = document.querySelector("[data-user-id]");
      if (userElement) {
        this.currentUser = {
          id: userElement.dataset.userId,
          username: userElement.dataset.username,
          displayName: userElement.dataset.displayName,
        };
        console.log(
          `👤 Current user: ${this.currentUser.displayName} (@${this.currentUser.username}) - ID: ${this.currentUser.id}`
        );
      }
    } catch (error) {
      console.error("❌ Error loading user data:", error);
    }
  }

  initializeSocket() {
    try {
      this.socket = io();

      this.socket.on("connect", () => {
        console.log("🔌 Connected to dashboard socket");
        this.updateConnectionStatus("connected");
        // Request initial notifications
        this.socket.emit("request_notifications");
      });

      this.socket.on("disconnect", () => {
        console.log("🔌 Disconnected from dashboard socket");
        this.updateConnectionStatus("disconnected");
      });

      this.socket.on("user_online", (data) => {
        console.log(`🟢 User online: ${data.user_id}`);
        this.updateFriendStatus(data.user_id, true);
      });

      this.socket.on("user_offline", (data) => {
        console.log(`🔴 User offline: ${data.user_id}`);
        this.updateFriendStatus(data.user_id, false);
      });

      this.socket.on("friend_request_received", (data) => {
        console.log(`📩 Friend request received from: ${data.from_username}`);
        this.showFriendRequestNotification(data);
        this.loadPendingRequests();
        this.loadNotifications(); // Refresh notifications
      });

      this.socket.on("friend_request_accepted", (data) => {
        console.log(`✅ Friend request accepted by: ${data.username}`);
        this.showFriendAcceptedNotification(data);
        this.loadFriendsList();
        this.loadPendingRequests();
        this.loadNotifications(); // Refresh notifications
      });

      this.socket.on("new_message", (data) => {
        console.log(`💬 New message in chat: ${data.chat_id}`);
        this.updateChatList(data);
      });

      this.socket.on("new_notification", (data) => {
        console.log(`🔔 New notification: ${data.message}`);
        this.handleNewNotification(data);
      });

      this.socket.on("notification_updated", (data) => {
        console.log(`🔄 Notification updated event received`);
        this.handleNotificationUpdated(data);
      });

      this.socket.on("notifications_data", (data) => {
        console.log(
          `📋 Received notifications data: ${data.notifications.length} notifications`
        );
        this.notifications = data.notifications;
        this.unreadNotificationCount = data.unread_count;
        this.updateNotificationUI();
      });

      this.socket.on("notifications_cleared", (data) => {
        console.log(`🔔 Notifications cleared for sender: ${data.sender_id}`);
        this.removeBellIcon(data.sender_id, false);
      });

      this.socket.on("new_message_notification", (data) => {
        console.log(
          `🔔 New message notification from: ${data.sender_username}`
        );
        this.addOrUpdateBellIcon(data);
      });

      this.socket.on("connect_error", (error) => {
        console.error("🔌 Socket connection error:", error);
        this.updateConnectionStatus("error");
      });
    } catch (error) {
      console.error("❌ Error initializing socket:", error);
    }
  }

  initializeEventListeners() {
    // Tab switching
    this.initializeTabs();

    // Navigation
    this.initializeNavigation();

    // Friend actions
    this.initializeFriendActions();

    // Global click handlers
    this.initializeGlobalClickHandlers();

    console.log("✅ Event listeners initialized");
  }

  initializeTabs() {
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", (e) => {
        e.preventDefault();
        const tabName = tab.dataset.tab || tab.textContent.toLowerCase();
        this.switchTab(tabName);
      });
    });

    // Set default tab
    this.switchTab("overview");
  }

  initializeNavigation() {
    // Logout button
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", (e) => {
        e.preventDefault();
        this.logout();
      });
    }

    // My Profile button
    const profileBtn = document.getElementById("profileBtn");
    if (profileBtn) {
      profileBtn.addEventListener("click", (e) => {
        e.preventDefault();
        this.viewMyProfile();
      });
    }

    // Start New Chat button
    const newChatBtn = document.getElementById("newChatBtn");
    if (newChatBtn) {
      newChatBtn.addEventListener("click", (e) => {
        e.preventDefault();
        this.startNewChat();
      });
    }
  }

  initializeFriendActions() {
    // Delegate friend action events
    document.addEventListener("click", (e) => {
      if (e.target.closest('[data-action="accept-request"]')) {
        const requestId =
          e.target.closest("[data-request-id]").dataset.requestId;
        this.respondToFriendRequest(requestId, "accept");
      }

      if (e.target.closest('[data-action="decline-request"]')) {
        const requestId =
          e.target.closest("[data-request-id]").dataset.requestId;
        this.respondToFriendRequest(requestId, "decline");
      }

      if (e.target.closest('[data-action="remove-friend"]')) {
        const friendId = e.target.closest("[data-friend-id]").dataset.friendId;
        this.removeFriend(friendId);
      }

      if (e.target.closest('[data-action="start-chat"]')) {
        const userId = e.target.closest("[data-user-id]").dataset.userId;
        this.startChatWithUser(userId);
      }
    });
  }

  initializeGlobalClickHandlers() {
    document.addEventListener("click", (e) => {
      // Handle chat item clicks
      if (e.target.closest(".chat-item")) {
        const chatItem = e.target.closest(".chat-item");
        const chatId = chatItem.dataset.chatId;
        if (chatId) {
          this.openChat(chatId);
        }
      }

      // Handle friend item clicks (excluding action buttons)
      if (
        e.target.closest(".friend-item") &&
        !e.target.closest(".friend-actions")
      ) {
        const friendItem = e.target.closest(".friend-item");
        const friendId = friendItem.dataset.friendId;
        if (friendId) {
          this.viewUserProfile(friendId);
        }
      }

      // Handle search result clicks
      if (e.target.closest(".search-result-info")) {
        const resultItem = e.target.closest(".search-result-item");
        const userId = resultItem.dataset.userId;
        if (userId) {
          this.viewUserProfile(userId);
        }
      }
    });
  }

  initializeSearch() {
    const searchInput = document.getElementById("searchInput");
    const searchResults = document.getElementById("searchResults");

    if (!searchInput || !searchResults) {
      console.error("❌ Search elements not found in DOM");
      return;
    }

    let searchTimeout;

    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchTimeout);
      const query = e.target.value.trim();

      console.log(`⌨️ Search input: "${query}" (length: ${query.length})`);

      if (query.length === 0) {
        searchResults.style.display = "none";
        return;
      }

      // Show immediate loading for better UX
      if (query.length >= 1) {
        this.showSearchLoading();
      }

      searchTimeout = setTimeout(() => {
        this.performSearch(query);
      }, 500);
    });

    // Handle Enter key for immediate search
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        clearTimeout(searchTimeout);
        const query = searchInput.value.trim();
        if (query) {
          this.performSearch(query);
        }
      }
    });

    // Hide search results when clicking outside
    document.addEventListener("click", (e) => {
      if (
        !searchInput.contains(e.target) &&
        !searchResults.contains(e.target)
      ) {
        searchResults.style.display = "none";
      }
    });

    console.log("✅ Search initialized");
  }

  initializeNotifications() {
    // Create notification bell if it doesn't exist
    if (!document.getElementById("notificationBell")) {
      this.createNotificationBell();
    }

    // Load initial notifications
    this.loadNotifications();

    // Set up polling for notifications
    setInterval(() => {
      this.loadUnreadCount();
    }, 30000); // Check every 30 seconds

    console.log("✅ Notifications system initialized");
  }

  createNotificationBell() {
    const sidebar = document.querySelector(".sidebar .user-header");
    if (!sidebar) return;

    const notificationHTML = `
      <div class="notification-header">
        <div class="notification-bell" id="notificationBell" onclick="dashboard.toggleNotifications()">
          <i class="fas fa-bell"></i>
          <span class="notification-badge" id="notificationBadge" style="display: none;">0</span>
        </div>
        <div class="notification-dropdown" id="notificationDropdown" style="display: none;">
          <div class="notification-header">
            <h4>Notifications</h4>
            <button class="btn btn-sm" onclick="dashboard.markAllNotificationsAsRead()">
              Mark all as read
            </button>
          </div>
          <div class="notification-list" id="notificationList">
            <div class="notification-loading">
              <div class="spinner"></div>
              <p>Loading notifications...</p>
            </div>
          </div>
          <div class="notification-footer">
            <a href="#" onclick="dashboard.loadMoreNotifications()">Load more</a>
          </div>
        </div>
      </div>
    `;

    // Insert after user header
    sidebar.insertAdjacentHTML("afterend", notificationHTML);
  }

  createBellIconsContainer() {
    // Remove existing container if it exists
    const existingContainer = document.getElementById("bellIconsContainer");
    if (existingContainer) {
      existingContainer.remove();
    }

    const container = document.createElement("div");
    container.id = "bellIconsContainer";
    container.className = "bell-icons-container";

    // Add styles
    container.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 1000;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-height: 300px;
      overflow-y: auto;
    `;

    document.body.appendChild(container);
    console.log("✅ Bell icons container created");
  }

  // Bell Icon Management Methods
  addOrUpdateBellIcon(notificationData) {
    const senderId = notificationData.sender_id;
    if (!senderId) return;

    console.log(`🔔 Processing bell icon for sender: ${senderId}`);

    // Check if we already have a bell icon for this sender
    if (this.bellIcons.has(senderId)) {
      // Update existing bell icon with new count
      this.updateBellIconCount(senderId, notificationData.message_count || 1);
    } else {
      // Create new bell icon
      this.createBellIcon(senderId, notificationData);
    }
  }

  createBellIcon(senderId, notificationData) {
    const bellIconsContainer = document.getElementById("bellIconsContainer");
    if (!bellIconsContainer) {
      console.error("❌ Bell icons container not found");
      return;
    }

    const bellIcon = document.createElement("div");
    bellIcon.className = "friend-bell-icon";
    bellIcon.dataset.senderId = senderId;
    bellIcon.innerHTML = `
      <div class="bell-icon-content">
        <i class="fas fa-bell"></i>
        <span class="bell-message-count">${
          notificationData.message_count || 1
        }</span>
        <span class="bell-sender-name">${
          notificationData.sender_username || "Unknown"
        }</span>
      </div>
      <button class="bell-close-btn" onclick="event.stopPropagation(); dashboard.removeBellIcon('${senderId}', true)">
        <i class="fas fa-times"></i>
      </button>
    `;

    // Add click handler to open chat
    bellIcon.addEventListener("click", (e) => {
      if (!e.target.closest(".bell-close-btn")) {
        this.openChatWithSender(senderId, notificationData.chat_id);
      }
    });

    bellIconsContainer.appendChild(bellIcon);
    this.bellIcons.set(senderId, bellIcon);

    console.log(`✅ Created bell icon for sender: ${senderId}`);
  }

  updateBellIconCount(senderId, newCount) {
    const bellIcon = this.bellIcons.get(senderId);
    if (bellIcon) {
      const countElement = bellIcon.querySelector(".bell-message-count");
      if (countElement) {
        countElement.textContent = newCount;
        console.log(`🔄 Updated bell icon count for ${senderId}: ${newCount}`);
      }
    }
  }

  removeBellIcon(senderId, markAsRead = false) {
    const bellIcon = this.bellIcons.get(senderId);
    if (bellIcon) {
      // Add removal animation
      bellIcon.classList.add("removing");

      setTimeout(() => {
        bellIcon.remove();
        this.bellIcons.delete(senderId);
        console.log(`✅ Removed bell icon for sender: ${senderId}`);
      }, 300); // Match CSS animation duration

      if (markAsRead && this.socket) {
        // Mark all notifications from this sender as read
        this.socket.emit("mark_all_message_notifications_read", {
          sender_id: senderId,
        });
      }
    }
  }

  openChatWithSender(senderId, chatId) {
    console.log(`💬 Opening chat with sender: ${senderId}, chat: ${chatId}`);

    if (chatId) {
      this.openChat(chatId);
    } else {
      // If no chatId, try to find or create a chat with this sender
      this.startChatWithUser(senderId);
    }

    // Remove the bell icon after opening chat
    this.removeBellIcon(senderId, true);
  }

  // Notification Management
  async loadNotifications() {
    try {
      const response = await fetch("/api/notifications?limit=10");
      if (!response.ok) throw new Error("Failed to load notifications");

      const data = await response.json();
      this.notifications = data.notifications;
      this.unreadNotificationCount = data.unread_count;
      this.updateNotificationUI();

      console.log(
        `✅ Loaded ${this.notifications.length} notifications (${this.unreadNotificationCount} unread)`
      );
    } catch (error) {
      console.error("❌ Error loading notifications:", error);
    }
  }

  async loadUnreadCount() {
    try {
      const response = await fetch("/api/notifications/unread-count");
      if (!response.ok) return;

      const data = await response.json();
      this.unreadNotificationCount = data.unread_count;
      this.updateNotificationBadge();
      this.checkAndRemoveNotificationIcon();
    } catch (error) {
      console.error("❌ Error loading unread count:", error);
    }
  }

  updateNotificationUI() {
    this.updateNotificationBadge();
    this.updateNotificationList();
    this.checkAndRemoveNotificationIcon();
  }

  updateNotificationBadge() {
    const badge = document.getElementById("notificationBadge");
    const bell = document.getElementById("notificationBell");

    if (badge) {
      if (this.unreadNotificationCount > 0) {
        badge.textContent =
          this.unreadNotificationCount > 99
            ? "99+"
            : this.unreadNotificationCount;
        badge.style.display = "flex";
        if (bell) {
          bell.classList.add("has-notifications");
        }
      } else {
        badge.style.display = "none";
        if (bell) {
          bell.classList.remove("has-notifications");
        }
      }
    }
  }

  updateNotificationList() {
    const notificationList = document.getElementById("notificationList");
    if (!notificationList) return;

    if (this.notifications.length === 0) {
      notificationList.innerHTML = `
        <div class="notification-empty">
          <i class="fas fa-bell-slash"></i>
          <p>No notifications</p>
          <p style="font-size: 0.8rem;">You're all caught up!</p>
        </div>
      `;
      return;
    }

    notificationList.innerHTML = this.notifications
      .map((notification) => {
        const messageCount = notification.data?.message_count || 1;
        const showCount = messageCount > 1;
        const senderId = notification.data?.sender_id;

        return `
          <div class="notification-item ${
            notification.is_read ? "" : "unread"
          }" 
               onclick="dashboard.handleNotificationClick('${
                 notification._id
               }', '${notification.type}', ${JSON.stringify(
          notification.data
        ).replace(/'/g, "\\'")})">
            <div class="notification-content">
              <div class="notification-icon">
                <i class="fas fa-${this.getNotificationIcon(
                  notification.type,
                  notification.data
                )}"></i>
                ${
                  showCount
                    ? `<span class="message-count-badge">${messageCount}</span>`
                    : ""
                }
              </div>
              <div class="notification-text">
                <div class="notification-message">${this.escapeHtml(
                  notification.message
                )}</div>
                ${
                  showCount
                    ? `<div class="notification-count">${messageCount} messages</div>`
                    : ""
                }
                <div class="notification-time">${this.formatTime(
                  notification.created_at
                )}</div>
                ${
                  !notification.is_read
                    ? `
                <div class="notification-actions">
                  <button class="btn btn-sm" onclick="event.stopPropagation(); dashboard.markNotificationAsRead('${
                    notification._id
                  }', '${senderId || ""}')">
                    Mark as read
                  </button>
                </div>
                `
                    : ""
                }
              </div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  getNotificationIcon(type, data = {}) {
    const icons = {
      new_message: "comment",
      friend_request: "user-plus",
      friend_request_accepted: "user-check",
      message_read: "eye",
    };

    let icon = icons[type] || "bell";

    // Add message count badge for consolidated notifications
    if (type === "new_message" && data.message_count > 1) {
      icon = "comments"; // Use comments icon for multiple messages
    }

    return icon;
  }

  toggleNotifications() {
    const dropdown = document.getElementById("notificationDropdown");
    if (!dropdown) return;

    if (dropdown.style.display === "none") {
      dropdown.style.display = "block";
      this.loadNotifications(); // Refresh when opening
    } else {
      dropdown.style.display = "none";
    }
  }

  async markNotificationAsRead(notificationId, senderId = null) {
    try {
      const response = await fetch("/api/notifications/mark-read", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          notification_id: notificationId,
        }),
      });

      const data = await response.json();
      if (data.success) {
        this.unreadNotificationCount = Math.max(
          0,
          this.unreadNotificationCount - 1
        );
        this.updateNotificationBadge();
        this.checkAndRemoveNotificationIcon();
        this.loadNotifications(); // Reload notifications

        // If senderId is provided and we have a bell icon for them, remove it
        if (senderId) {
          this.removeBellIcon(senderId, false);
        }
      } else {
        this.showNotification("Failed to mark notification as read", "error");
      }
    } catch (error) {
      console.error("❌ Error marking notification as read:", error);
      this.showNotification("Error marking notification as read", "error");
    }
  }

  async markAllNotificationsAsRead() {
    try {
      const response = await fetch("/api/notifications/mark-all-read", {
        method: "POST",
      });

      const data = await response.json();
      if (data.success) {
        this.showNotification(
          `Marked ${data.marked_count} notifications as read`,
          "success"
        );
        this.unreadNotificationCount = 0;
        this.updateNotificationBadge();
        this.checkAndRemoveNotificationIcon();

        // Remove all bell icons
        this.bellIcons.forEach((bellIcon, senderId) => {
          this.removeBellIcon(senderId, false);
        });

        this.loadNotifications(); // Reload notifications
      } else {
        this.showNotification(
          "Failed to mark all notifications as read",
          "error"
        );
      }
    } catch (error) {
      console.error("❌ Error marking all notifications as read:", error);
      this.showNotification("Error marking all notifications as read", "error");
    }
  }

  handleNotificationClick(notificationId, type, data) {
    const senderId = data.sender_id;

    // Mark as read
    this.markNotificationAsRead(notificationId, senderId);

    // Handle different notification types
    switch (type) {
      case "new_message":
        // Remove bell icon for this sender
        if (senderId) {
          this.removeBellIcon(senderId, false);
        }
        // Redirect to chat
        if (data.chat_id) {
          window.location.href = `/chat/${data.chat_id}`;
        }
        break;
      case "friend_request":
        // Show friend requests tab
        this.switchTab("friends");
        break;
      case "friend_request_accepted":
        // Refresh friends list
        this.loadFriendsList();
        break;
    }

    // Close dropdown
    const dropdown = document.getElementById("notificationDropdown");
    if (dropdown) {
      dropdown.style.display = "none";
    }
  }

  handleNewNotification(notificationData) {
    // For message notifications, handle bell icons
    if (notificationData.type === "new_message" || notificationData.sender_id) {
      this.addOrUpdateBellIcon(notificationData);
    }

    // Show toast notification
    this.showNotification(notificationData.message, "info");

    // Update badge
    this.unreadNotificationCount++;
    this.updateNotificationBadge();

    // Add to notifications list if dropdown is open
    const dropdown = document.getElementById("notificationDropdown");
    if (dropdown && dropdown.style.display === "block") {
      this.loadNotifications(); // Reload to get the new notification
    }
  }

  handleNotificationUpdated(data) {
    console.log(`🔄 Notification updated: ${data.type}`);

    if (data.type === "message_count_updated") {
      // Update the notification badge without showing a new notification
      this.unreadNotificationCount++;
      this.updateNotificationBadge();

      // Refresh notifications if dropdown is open
      const dropdown = document.getElementById("notificationDropdown");
      if (dropdown && dropdown.style.display === "block") {
        this.loadNotifications();
      }
    }
  }

  checkAndRemoveNotificationIcon() {
    if (this.unreadNotificationCount === 0) {
      const notificationBell = document.getElementById("notificationBell");
      const notificationBadge = document.getElementById("notificationBadge");

      if (notificationBell) {
        notificationBell.classList.remove("has-notifications");
      }
      if (notificationBadge) {
        notificationBadge.style.display = "none";
      }
    }
  }

  // Search functionality
  async performSearch(query) {
    const searchInput = document.getElementById("searchInput");
    const searchResults = document.getElementById("searchResults");

    if (!query) {
      searchResults.style.display = "none";
      return;
    }

    console.log(`🔍 Performing search for: "${query}"`);

    try {
      this.showSearchLoading();

      const response = await fetch("/api/search-users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: query }),
      });

      console.log(`📡 Search response status: ${response.status}`);

      if (!response.ok) {
        throw new Error(`Search request failed: ${response.status}`);
      }

      const data = await response.json();
      console.log(`📊 Search API returned:`, data);

      if (data.users && data.users.length > 0) {
        console.log(`✅ Displaying ${data.users.length} search results`);
        this.displaySearchResults(data.users);
      } else {
        console.log(`❌ No users found for query: "${query}"`);
        this.displayNoSearchResults(query);
      }
    } catch (error) {
      console.error("🔴 Search error:", error);
      this.displaySearchError(error.message);
    }
  }

  displaySearchResults(users) {
    const searchResults = document.getElementById("searchResults");
    let html = "";

    console.log(`🎨 Rendering ${users.length} users in search results`);

    users.forEach((user) => {
      const statusClass = user.is_online ? "status-online" : "status-offline";
      const statusText = user.is_online ? "Online" : "Offline";
      const displayName = user.display_name || user.username;
      const isCurrentUser = user.is_current_user || false;

      console.log(
        `👤 Rendering user: ${displayName} (@${user.username}) - Current: ${isCurrentUser} - ID: ${user._id}`
      );

      html += `
                <div class="search-result-item ${
                  isCurrentUser ? "current-user-item" : ""
                }" data-user-id="${user._id}">
                    <div class="search-result-avatar">
                        ${displayName[0].toUpperCase()}
                    </div>
                    <div class="search-result-info">
                        <div class="search-result-name">
                            ${this.escapeHtml(displayName)}
                            ${
                              isCurrentUser
                                ? '<span class="current-user-badge">(You)</span>'
                                : ""
                            }
                        </div>
                        <div class="search-result-username">@${this.escapeHtml(
                          user.username
                        )}</div>
                        <div class="search-result-userid">
                            <small><strong>User ID:</strong> ${user._id}</small>
                        </div>
                        <div class="search-result-status ${statusClass}">
                            <i class="fas fa-circle"></i> ${statusText}
                        </div>
                        ${
                          user.status
                            ? `<div class="search-result-bio">${this.escapeHtml(
                                user.status
                              )}</div>`
                            : ""
                        }
                    </div>
                    <div class="search-result-actions">
                        ${
                          isCurrentUser
                            ? `
                            <button class="btn btn-primary btn-sm" onclick="dashboard.viewMyProfile()">
                                <i class="fas fa-user"></i> My Profile
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="dashboard.copyUserId('${user._id}')">
                                <i class="fas fa-copy"></i> Copy ID
                            </button>
                        `
                            : user.is_friend
                            ? `
                            <button class="btn btn-primary btn-sm" onclick="dashboard.startChatWithUser('${user._id}')">
                                <i class="fas fa-comment"></i> Message
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="dashboard.copyUserId('${user._id}')">
                                <i class="fas fa-copy"></i> Copy ID
                            </button>
                        `
                            : `
                            <button class="btn btn-primary btn-sm" onclick="dashboard.sendFriendRequest('${user._id}')">
                                <i class="fas fa-user-plus"></i> Add Friend
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="dashboard.copyUserId('${user._id}')">
                                <i class="fas fa-copy"></i> Copy ID
                            </button>
                        `
                        }
                    </div>
                </div>
            `;
    });

    searchResults.innerHTML = html;
    searchResults.style.display = "block";
    console.log(`✅ Search results displayed`);
  }

  displayNoSearchResults(query) {
    const searchResults = document.getElementById("searchResults");
    searchResults.innerHTML = `
            <div class="search-no-results">
                <i class="fas fa-search" style="font-size: 2rem; margin-bottom: 8px;"></i>
                <p>No users found for "${query}"</p>
                <p style="font-size: 0.8rem; color: var(--text-light);">Try searching by exact username</p>
                <div style="margin-top: 1rem; font-size: 0.8rem; color: var(--text-light);">
                    <p><strong>Your username:</strong> ${
                      this.currentUser?.username || "Unknown"
                    }</p>
                    <p><strong>Your user ID:</strong> ${
                      this.currentUser?.id || "Unknown"
                    }</p>
                </div>
            </div>
        `;
    searchResults.style.display = "block";
  }

  displaySearchError(errorMessage) {
    const searchResults = document.getElementById("searchResults");
    searchResults.innerHTML = `
            <div class="search-no-results">
                <i class="fas fa-exclamation-triangle" style="font-size: 2rem; margin-bottom: 8px; color: var(--error);"></i>
                <p>Search failed</p>
                <p style="font-size: 0.8rem; color: var(--text-light);">${errorMessage}</p>
                <button class="btn btn-primary btn-sm" onclick="dashboard.retrySearch()" style="margin-top: 0.5rem;">
                    <i class="fas fa-redo"></i> Try Again
                </button>
            </div>
        `;
    searchResults.style.display = "block";
  }

  showSearchLoading() {
    const searchResults = document.getElementById("searchResults");
    searchResults.innerHTML = `
            <div class="search-no-results">
                <div class="spinner" style="margin: 0 auto 1rem auto;"></div>
                <p>Searching...</p>
            </div>
        `;
    searchResults.style.display = "block";
  }

  retrySearch() {
    const searchInput = document.getElementById("searchInput");
    if (searchInput.value.trim()) {
      this.performSearch(searchInput.value.trim());
    }
  }

  async loadDashboardData() {
    console.log("📊 Loading dashboard data...");
    await Promise.all([
      this.loadFriendsList(),
      this.loadChatsList(),
      this.loadPendingRequests(),
    ]);
    console.log("✅ Dashboard data loaded");
  }

  async loadFriendsList() {
    try {
      console.log("👥 Loading friends list...");
      const response = await fetch("/api/friends");
      if (!response.ok) throw new Error("Failed to load friends");

      const data = await response.json();
      this.friends = data.friends || [];
      console.log(`✅ Loaded ${this.friends.length} friends`);
      this.renderFriendsList();
    } catch (error) {
      console.error("❌ Error loading friends:", error);
      this.showError("Failed to load friends");
    }
  }

  renderFriendsList() {
    const friendsList = document.getElementById("friendsList");
    if (!friendsList) return;

    if (this.friends.length === 0) {
      friendsList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-user-friends"></i>
                    <p>No friends yet</p>
                    <p style="font-size: 0.9rem;">Search for users to add friends</p>
                </div>
            `;
      return;
    }

    friendsList.innerHTML = this.friends
      .map(
        (friend) => `
            <div class="friend-item" data-friend-id="${friend._id}">
                <div class="friend-avatar">
                    ${
                      friend.display_name
                        ? friend.display_name[0].toUpperCase()
                        : friend.username[0].toUpperCase()
                    }
                </div>
                <div class="friend-info">
                    <div class="friend-name">${this.escapeHtml(
                      friend.display_name || friend.username
                    )}</div>
                    <div class="friend-status">
                        ${
                          friend.is_online
                            ? `<span class="status-online"><i class="fas fa-circle"></i> Online - ${this.escapeHtml(
                                friend.status || "Available"
                              )}</span>`
                            : `<span class="status-offline"><i class="fas fa-circle"></i> Offline</span>`
                        }
                    </div>
                </div>
                <div class="friend-actions">
                    <button class="friend-action-btn" onclick="dashboard.startChatWithUser('${
                      friend._id
                    }')" title="Message">
                        <i class="fas fa-comment"></i>
                    </button>
                    <button class="friend-action-btn" onclick="dashboard.viewUserProfile('${
                      friend._id
                    }')" title="Profile">
                        <i class="fas fa-user"></i>
                    </button>
                    <button class="friend-action-btn delete" onclick="dashboard.removeFriend('${
                      friend._id
                    }')" title="Remove">
                        <i class="fas fa-user-minus"></i>
                    </button>
                </div>
            </div>
        `
      )
      .join("");
  }

  async loadChatsList() {
    try {
      // Chats are loaded server-side, just update any dynamic data
      this.updateChatsBadges();
      console.log("💬 Chats list loaded");
    } catch (error) {
      console.error("❌ Error loading chats:", error);
    }
  }

  async loadPendingRequests() {
    try {
      // Pending requests are loaded server-side
      this.updatePendingRequestsBadge();
      console.log("📩 Pending requests loaded");
    } catch (error) {
      console.error("❌ Error loading pending requests:", error);
    }
  }

  updateChatsBadges() {
    const unreadCount = this.chats.filter(
      (chat) => chat.unread_count > 0
    ).length;
    const badge = document.getElementById("chatsBadge");
    if (badge) {
      badge.textContent = unreadCount;
      badge.style.display = unreadCount > 0 ? "inline" : "none";
    }
  }

  updatePendingRequestsBadge() {
    const pendingCount = document.querySelectorAll(".request-item").length;
    const badge = document.getElementById("pendingRequestsBadge");
    if (badge) {
      badge.textContent = pendingCount;
      badge.style.display = pendingCount > 0 ? "inline" : "none";
    }
  }

  // Tab Management
  switchTab(tabName) {
    console.log(`📑 Switching to tab: ${tabName}`);

    // Hide all tab contents
    document.querySelectorAll(".tab-content").forEach((content) => {
      content.style.display = "none";
    });

    // Remove active class from all tabs
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.classList.remove("active");
    });

    // Show selected tab content
    const selectedContent = document.getElementById(`${tabName}Tab`);
    if (selectedContent) {
      selectedContent.style.display = "block";
    }

    // Activate selected tab
    const selectedTab = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedTab) {
      selectedTab.classList.add("active");
    }

    // Load tab-specific data
    this.loadTabData(tabName);
  }

  loadTabData(tabName) {
    console.log(`📊 Loading data for tab: ${tabName}`);
    switch (tabName) {
      case "friends":
        this.loadFriendsList();
        break;
      case "chats":
        this.loadChatsList();
        break;
      case "groups":
        // Load groups data
        break;
    }
  }

  // Friend Management
  async sendFriendRequest(userId) {
    try {
      console.log(`📤 Sending friend request to: ${userId}`);
      const response = await fetch("/api/send-friend-request", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ user_id: userId }),
      });

      const data = await response.json();

      if (data.success) {
        this.showNotification("Friend request sent!", "success");
        document.getElementById("searchResults").style.display = "none";
        document.getElementById("searchInput").value = "";
      } else {
        this.showNotification(
          data.error || "Failed to send friend request",
          "error"
        );
      }
    } catch (error) {
      console.error("❌ Error sending friend request:", error);
      this.showNotification("Error sending friend request", "error");
    }
  }

  async respondToFriendRequest(requestId, action) {
    try {
      console.log(`📝 Responding to friend request ${requestId}: ${action}`);
      const response = await fetch("/api/respond-friend-request", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          request_id: requestId,
          action: action,
        }),
      });

      const data = await response.json();

      if (data.success) {
        this.showNotification(`Friend request ${action}ed`, "success");
        this.loadPendingRequests();
        this.loadFriendsList();
      } else {
        this.showNotification(
          data.error || `Failed to ${action} friend request`,
          "error"
        );
      }
    } catch (error) {
      console.error(`❌ Error responding to friend request:`, error);
      this.showNotification("Error processing request", "error");
    }
  }

  async removeFriend(friendId) {
    if (!confirm("Are you sure you want to remove this friend?")) {
      return;
    }

    try {
      console.log(`🗑️ Removing friend: ${friendId}`);
      const response = await fetch("/api/remove-friend", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ friend_id: friendId }),
      });

      const data = await response.json();

      if (data.success) {
        this.showNotification("Friend removed", "success");
        this.loadFriendsList();
      } else {
        this.showNotification(data.error || "Failed to remove friend", "error");
      }
    } catch (error) {
      console.error("❌ Error removing friend:", error);
      this.showNotification("Error removing friend", "error");
    }
  }

  // Chat Management
  async startChatWithUser(userId) {
    try {
      console.log(`💬 Starting chat with user: ${userId}`);
      const response = await fetch("/api/create-chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          participants: [userId],
          is_group: false,
        }),
      });

      const data = await response.json();

      if (data.chat_id) {
        window.location.href = `/chat/${data.chat_id}`;
      } else {
        this.showNotification("Failed to start chat", "error");
      }
    } catch (error) {
      console.error("❌ Error starting chat:", error);
      this.showNotification("Error starting chat", "error");
    }
  }

  startNewChat() {
    console.log("🆕 Starting new chat");
    // Implementation for starting new chat modal
    this.showNotification("New chat feature coming soon!", "info");
  }

  openChat(chatId) {
    console.log(`💬 Opening chat: ${chatId}`);
    window.location.href = `/chat/${chatId}`;
  }

  // User Navigation
  viewUserProfile(userId) {
    console.log(`👤 Viewing user profile: ${userId}`);
    window.location.href = `/user/${userId}`;
  }

  viewMyProfile() {
    console.log(`👤 Viewing my own profile`);
    window.location.href = "/my-profile";
  }

  copyUserId(userId) {
    navigator.clipboard
      .writeText(userId)
      .then(() => {
        this.showNotification("User ID copied to clipboard!", "success");
      })
      .catch((err) => {
        console.error("Failed to copy user ID: ", err);
        this.showNotification("Failed to copy user ID", "error");
      });
  }

  // Socket Event Handlers
  updateFriendStatus(userId, isOnline) {
    console.log(
      `🔄 Updating friend status: ${userId} -> ${
        isOnline ? "online" : "offline"
      }`
    );
    const friendItems = document.querySelectorAll(
      `[data-friend-id="${userId}"]`
    );
    friendItems.forEach((item) => {
      const statusElement = item.querySelector(".friend-status");
      if (statusElement) {
        if (isOnline) {
          statusElement.innerHTML =
            '<span class="status-online"><i class="fas fa-circle"></i> Online</span>';
        } else {
          statusElement.innerHTML =
            '<span class="status-offline"><i class="fas fa-circle"></i> Offline</span>';
        }
      }
    });
  }

  updateChatList(messageData) {
    console.log(`💬 Updating chat list for message: ${messageData.chat_id}`);
    // Update chat list when new message arrives
    const chatItem = document.querySelector(
      `[data-chat-id="${messageData.chat_id}"]`
    );
    if (chatItem) {
      const lastMessageElement = chatItem.querySelector(".chat-last-message");
      if (lastMessageElement) {
        lastMessageElement.textContent = messageData.content;
      }

      // Move chat to top
      const chatsList = document.getElementById("chatsList");
      if (chatsList && chatItem.parentNode === chatsList) {
        chatsList.insertBefore(chatItem, chatsList.firstChild);
      }
    }
  }

  showFriendRequestNotification(data) {
    console.log(
      `📩 Showing friend request notification from: ${data.from_username}`
    );
    this.showNotification(
      `New friend request from ${data.from_username}`,
      "info"
    );
    this.updatePendingRequestsBadge();
  }

  showFriendAcceptedNotification(data) {
    console.log(`✅ Showing friend accepted notification: ${data.username}`);
    this.showNotification(
      `${data.username} accepted your friend request!`,
      "success"
    );
  }

  // UI Utilities
  showNotification(message, type = "info") {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll(
      ".dashboard-notification"
    );
    existingNotifications.forEach((notification) => notification.remove());

    const notification = document.createElement("div");
    notification.className = `dashboard-notification notification-${type}`;
    notification.innerHTML = `
            <div class="notification-content">
                <i class="fas fa-${this.getNotificationIcon(type)}"></i>
                <span>${message}</span>
                <button class="notification-close" onclick="this.parentElement.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

    document.body.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
      if (notification.parentElement) {
        notification.remove();
      }
    }, 5000);
  }

  getNotificationIcon(type) {
    const icons = {
      success: "check-circle",
      error: "exclamation-triangle",
      warning: "exclamation-circle",
      info: "info-circle",
    };
    return icons[type] || "info-circle";
  }

  showError(message) {
    this.showNotification(message, "error");
  }

  updateConnectionStatus(status) {
    const statusElement = document.getElementById("connectionStatus");
    if (statusElement) {
      statusElement.textContent =
        status.charAt(0).toUpperCase() + status.slice(1);
      statusElement.className = `connection-status status-${status}`;
    }
  }

  logout() {
    if (confirm("Are you sure you want to logout?")) {
      console.log("🚪 Logging out...");
      window.location.href = "/logout";
    }
  }

  escapeHtml(unsafe) {
    if (!unsafe) return "";
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Utility Methods
  formatTime(timestamp) {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) return "Just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString();
  }

  formatDate(timestamp) {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return `${days} days ago`;

    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }
}

// Initialize dashboard when DOM is loaded
let dashboard;

document.addEventListener("DOMContentLoaded", function () {
  console.log("📄 DOM fully loaded, initializing dashboard...");
  dashboard = new DashboardManager();
  window.dashboard = dashboard;
});

// Global functions for template onclick handlers
function showTab(tabName) {
  if (dashboard) {
    dashboard.switchTab(tabName);
  }
}

function openChat(chatId) {
  if (dashboard) {
    dashboard.openChat(chatId);
  } else {
    window.location.href = `/chat/${chatId}`;
  }
}

function startNewChat() {
  if (dashboard) {
    dashboard.startNewChat();
  }
}

function respondToRequest(requestId, action) {
  if (dashboard) {
    dashboard.respondToFriendRequest(requestId, action);
  }
}

function viewUserProfile(userId) {
  if (dashboard) {
    dashboard.viewUserProfile(userId);
  } else {
    window.location.href = `/user/${userId}`;
  }
}

function sendFriendRequest(userId) {
  if (dashboard) {
    dashboard.sendFriendRequest(userId);
  }
}

function startChatWithUser(userId) {
  if (dashboard) {
    dashboard.startChatWithUser(userId);
  }
}

function copyUserId(userId) {
  if (dashboard) {
    dashboard.copyUserId(userId);
  }
}

// Export for use in other modules
if (typeof module !== "undefined" && module.exports) {
  module.exports = { DashboardManager };
}
