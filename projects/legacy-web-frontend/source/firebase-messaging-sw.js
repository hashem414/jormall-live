// firebase-messaging-sw.js
// Service Worker for handling background push notifications (Firebase Cloud Messaging)

importScripts("https://www.gstatic.com/firebasejs/10.13.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging-compat.js");

// ✅ Initialize Firebase (use exactly your project credentials)
firebase.initializeApp({
  apiKey: "REDACTED_CONFIGURE_LOCALLY",
  authDomain: "jormall-app.firebaseapp.com",
  projectId: "jormall-app",
  storageBucket: "jormall-app.appspot.com", 
  messagingSenderId: "983203637883",
  appId: "1:983203637883:web:bccf9f4e956870b2e650de",
  measurementId: "G-VGTRLJ03E4",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log('[SW] Background message:', payload);

  const notification = payload.notification;
  self.registration.showNotification(notification.title, {
    body: notification.body,
    icon: '/icons/icon-192.png',
  });
});