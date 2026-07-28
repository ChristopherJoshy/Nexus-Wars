import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth, initializeAuth, browserLocalPersistence, indexedDBLocalPersistence } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyBI8ZUZqi3u5mARodzTjySVvBKOkrZYwnw",
  authDomain: "nexuswars2026.firebaseapp.com",
  projectId: "nexuswars2026",
  storageBucket: "nexuswars2026.firebasestorage.app",
  messagingSenderId: "488591411882",
  appId: "1:488591411882:web:6c6fdada0b0c3c10031ed3",
  measurementId: "G-K9NQCR6Q19",
};

const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();

export const auth = (() => {
  if (typeof window !== "undefined") {
    try {
      return getAuth(app);
    } catch {
      return initializeAuth(app, {
        persistence: [indexedDBLocalPersistence, browserLocalPersistence],
      });
    }
  }
  return getAuth(app);
})();
