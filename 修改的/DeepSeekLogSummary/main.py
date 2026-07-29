from . import message


class Event:
    def init(plugin_event, Proc):
        message.handle_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        pass

    def group_message(plugin_event, Proc):
        message.handle_group_message(plugin_event, Proc)

    def save(plugin_event, Proc):
        message.handle_save(plugin_event, Proc)

    def menu(plugin_event, Proc):
        message.handle_menu(plugin_event, Proc)
