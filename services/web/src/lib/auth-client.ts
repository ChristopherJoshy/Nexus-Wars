import { auth } from "./firebase-client";
import {
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  signOut as fbSignOut,
  onIdTokenChanged,
} from "firebase/auth";
import { useEffect, useState } from "react";

const googleProvider = new GoogleAuthProvider();

export const signIn = {
  social: async ({ provider }: { provider: string }) => {
    if (provider !== "google") return;
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (e: unknown) {
      if (e instanceof Error && "code" in e && (e as { code: string }).code === "auth/popup-blocked") {
        await signInWithRedirect(auth, googleProvider);
      } else {
        throw e;
      }
    }
  },
};

export async function signOut() {
  await fbSignOut(auth);
}

export function useSession() {
  const [state, setState] = useState<{
    data: {
      user: {
        id: string;
        email: string | null;
        name: string | null;
        image: string | null;
      };
      token: string;
    } | null;
    isPending: boolean;
  }>({ data: null, isPending: true });

  useEffect(() => {
    const unsubscribe = onIdTokenChanged(auth, async (user) => {
      if (user) {
        const token = await user.getIdToken();
        setState({
          data: {
            user: {
              id: user.uid,
              email: user.email,
              name: user.displayName,
              image: user.photoURL,
            },
            token,
          },
          isPending: false,
        });
      } else {
        setState({ data: null, isPending: false });
      }
    });
    return unsubscribe;
  }, []);

  return state;
}
