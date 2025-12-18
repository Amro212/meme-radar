from notify import Notifier

def test():
    print("Testing Telegram Notification...")
    n = Notifier()
    if n.send("🔔 Trend Catcher: Testing notification system."):
        print("SUCCESS: Message sent.")
    else:
        print("FAIL: Message NOT sent. Check logs.")

if __name__ == "__main__":
    test()
