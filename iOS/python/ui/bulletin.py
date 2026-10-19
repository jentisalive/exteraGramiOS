from ios_bridge import command


class BulletinHelper:
    @staticmethod
    def show_success(text):
        command("bulletin", text=str(text), style="success")

    @staticmethod
    def show_info(text):
        command("bulletin", text=str(text), style="info")

    @staticmethod
    def show_error(text):
        command("bulletin", text=str(text), style="error")
