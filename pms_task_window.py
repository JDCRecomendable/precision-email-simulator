import csv
import datetime
import os
import random
import sys
import time
import webbrowser
from pathlib import Path

import pandas as pd
from PySide6 import QtGui, QtCore, QtWidgets, QtWebChannel, QtWebEngineWidgets
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem, QStyleOptionViewItem, QStyle
from plyer import notification
from pygame import mixer

LAUNCH_TIME = datetime.datetime.now()
COL_NAMES = ['ID', 'name', 'from', 'to', 'title', 'content', 'attachment', 'star', 'time', 'readState', 'category']
LOG_FILE_NAME = ''
DATE_FORMAT = '%Y-%m-%d'
LONG_TIME_FORMAT = '%H-%M-%S'
SHORT_TIME_FORMAT = '%H:%M'


class TaskWindow(QtWidgets.QWidget):

    def __init__(self, user_name, config):
        super(TaskWindow, self).__init__()

        self.channel = None
        self.count_down_counter = None
        self.file_name = None
        self.folder_path = None
        self.primary_task = None
        self.respond_window = None
        self.running = None

        self.username = user_name
        self.config = config
        self.save_location = self.config.get('saveLocation')

        self.ui = QUiLoader().load('resources/UI_files/main_page.ui')

        if self.username == '':
            self.username = 'no_user_name'
        self.emails = pd.read_csv(self.config.get('emailListLocation'))
        self.emails['star'] = self.emails['star'].astype('bool')

        self.current_emails = pd.DataFrame()
        self.incoming_emails = pd.DataFrame()
        self.incoming_interval = 0
        self.previous_emails = []
        self.current_email = None
        self.hovered_url = 'none'
        self.audio_notification_times = []
        self.session_timer = QtCore.QTimer(self)
        self.incoming_email_timer = QtCore.QTimer(self)
        self.reported_emails = []
        # ========== set up interface elements ===========
        mixer.init()
        self.beep = mixer.Sound("./resources/beep.wav")

        # set top buttons
        self.ui.starBtn.clicked.connect(self.star_btn_clicked)
        self.ui.deleteBtn.clicked.connect(self.delete_btn_click)
        self.ui.unreadBtn.clicked.connect(self.unread_btn_click)
        self.ui.reportBtn.clicked.connect(self.report_btn_click)
        self.ui.nextBtn.clicked.connect(self.next_btn_click)

        # set reply buttons
        self.ui.replyBtn.clicked.connect(lambda: self.respond_btn_clicked('reply'))
        self.ui.replyToAllBtn.clicked.connect(lambda: self.respond_btn_clicked('reply_to_all'))
        self.ui.forwardBtn.clicked.connect(lambda: self.respond_btn_clicked('forward'))

        self.ui.emailList.clicked.connect(self.email_table_clicked)

        # ==============================
        self.create_log_file()

        self.session_list = list(self.config.get('sessions').keys())
        self.current_session = self.session_list[0]

        self.setup_session()

    # ================================================================================================

    # ======== set up session ===================
    def get_current_session(self):
        return self.config.get('sessions').get(self.current_session)

    def setup_session_timer(self, session_config):
        self.session_timer = QtCore.QTimer(self)
        self.count_down_counter = int(session_config.get('duration')) * 60
        self.running = True
        self.session_timer.timeout.connect(self.timer_count_down)
        self.session_timer.start(1000)

    def timer_count_down(self):
        if self.running:
            self.count_down_counter -= 1

            if self.count_down_counter == 0:
                self.running = False
                print("completed")
                self.log_email("finish " + self.get_current_session().get('name'))
                self.save_primary_task_data_local()
                print(self.current_session)

                if self.get_current_session().get('endSessionPopup') != '':
                    message_notification(self,
                                         self.get_current_session().get('endSessionPopup'))

            # add some notification for countdown
            elif (self.count_down_counter / 60) in self.audio_notification_times:
                self.beep.play()

            if self.count_down_counter % 60 < 10:
                timer_str = str(int(self.count_down_counter / 60)) + ':0' + str(self.count_down_counter % 60)
            else:
                timer_str = str(int(self.count_down_counter / 60)) + ':' + str(self.count_down_counter % 60)

            self.ui.timerLabel.setText(timer_str)

    def next_btn_click(self):
        print('next button clicked')
        print(self.current_session)
        if self.incoming_email_timer.isActive():  # turn off the incoming email timer
            self.incoming_email_timer.stop()
        self.count_down_counter = 1

    def setup_incoming_email_timer(self, session_config):
        print('setting up incoming timer')

        # set up timers for in coming emails
        self.incoming_email_timer = QtCore.QTimer()

        self.incoming_email_timer.timeout.connect(self.incoming_timer)
        print('cccc')
        print(session_config.get('incomingInterval'))
        self.incoming_email_timer.start(int(1000 * 60 * float(session_config.get('incomingInterval'))))

    def incoming_timer(self):
        if self.incoming_emails.shape[0] > 0:
            print('addEmail')
            self.incoming_emails = self.add_email(self.incoming_emails)
            self.set_unread_email_count()

            if self.incoming_emails.shape[0] == 0:
                print("timer stoped")
                self.incoming_email_timer.stop()

    def setup_session(self):
        session_config = self.get_current_session()
        self.setup_session_timer(session_config)

        self.ui.URLDisplay.setHidden(True)

        if session_config.get('audioNotification') != '':
            self.audio_notification_times = [int(x) for x in session_config.get('audioNotification').split(',')]

        if session_config.get('timeCountDown'):
            self.ui.timerLabel.setHidden(False)
        else:
            self.ui.timerLabel.setHidden(True)

        if session_config.get('incomingEmails'):
            self.setup_incoming_email_timer(session_config)

        for display, btn in zip(
                [session_config.get('starBtn'), session_config.get('reportBtn'), session_config.get('deleteBtn'),
                 session_config.get('unreadBtn')],
                [self.ui.starBtn, self.ui.reportBtn, self.ui.deleteBtn, self.ui.unreadBtn]):
            if not display:
                btn.hide()
            else:
                btn.show()

        # setup emails in the initial inbox
        self.setup_emails(session_config)
        self.set_up_email_timestamp()

        self.set_up_email_list_table()
        self.log_email("start " + self.current_session)
        if session_config.get('primaryTaskHtml') != '':
            self.ui.primaryTaskW.show()
            self.setup_primary_task()
        else:
            self.ui.primaryTaskW.hide()

    def setup_emails(self, session_config):
        self.current_emails = self.emails[
            (self.emails['ID'] >= int(session_config.get('legitEmails').get('emailListRange').get('start'))) &
            (self.emails['ID'] <= int(session_config.get('legitEmails').get('emailListRange').get('finish')))]
        if session_config.get('legitEmails').get('shuffleEmails'):
            self.current_emails = self.current_emails.sample(frac=1).reset_index(drop=True)

        if session_config.get('incomingEmails'):
            self.incoming_emails = self.emails[
                (self.emails['ID'] >= int(session_config.get('legitEmails').get('incomingRange').get('start'))) &
                (self.emails['ID'] <= int(session_config.get('legitEmails').get('incomingRange').get('finish')))]
            if session_config.get('legitEmails').get('shuffleEmails'):
                self.incoming_emails = self.incoming_emails.sample(frac=1).reset_index(drop=True)

        if session_config.get('hasPhishEmails'):
            self.add_phishing_emails_to_list(session_config)

        self.current_emails = self.current_emails.sort_index().reset_index(drop=True)
        print(self.incoming_emails)
        print('bbbbb')
        print(len(self.incoming_emails))
        if len(self.incoming_emails) != 0:
            self.incoming_emails = self.incoming_emails.sort_index().reset_index(drop=True)

    def add_phishing_emails_to_list(self, session_config):
        p_email_inbox_id = [int(x) for x in session_config.get('phishEmails').get('emailList').split(',')]
        if session_config.get('phishEmails').get('incomingList') != '':
            p_email_incoming_id = [int(x) for x in session_config.get('phishEmails').get('incomingList').split(',')]
        else:
            p_email_incoming_id = []
        p_email_inbox = self.emails[self.emails['ID'].isin(p_email_inbox_id)]
        p_email_incoming = self.emails[self.emails['ID'].isin(p_email_incoming_id)]

        if session_config.get('phishEmails').get('shuffleEmails'):
            print('shuffle p emails')
            p_email_inbox = p_email_inbox.sample(frac=1).reset_index(drop=True)
            p_email_inbox = p_email_inbox.iloc[:int(session_config.get('phishEmails').get('emailListNum'))]
            p_email_incoming = p_email_incoming.sample(frac=1).reset_index(drop=True)
            p_email_incoming = p_email_incoming.iloc[:int(session_config.get('phishEmails').get('incomingNum'))]

        self.current_emails = self.insert_p_email_to_list(p_email_inbox, self.current_emails, 'emailListLocations', session_config)
        if session_config.get('incomingEmails'):
            self.incoming_emails = self.insert_p_email_to_list(p_email_incoming, self.incoming_emails, 'incomingLocations', session_config)

    @staticmethod
    def insert_p_email_to_list(plist, elist, location, session_config):
        if session_config.get('phishEmails').get('randomLoc'):
            for index, row in plist.iterrows():
                ran_int = random.randint(0, elist.shape[0])
                elist.loc[ran_int + 0.5] = row
                elist = elist.sort_index().reset_index(drop=True)
        else:
            if session_config.get('phishEmails').get(location) != '':
                loc_list = [int(x) for x in session_config.get('phishEmails').get(location).split(',')]
            else:
                loc_list = []
            for i in range(0, len(loc_list)):
                elist.loc[loc_list[i] - 1.5] = plist.iloc[0]
                plist = plist.iloc[1:]
                elist = elist.sort_index().reset_index(drop=True)
        return elist

    # =======================  email set up ===============================================

    def add_email(self, email_list):
        print('----------------- email add notification --------------------------')
        if email_list.shape[0] > 0:
            item = email_list.iloc[0]
            self.current_emails = self.current_emails.append(item, ignore_index=True)
            self.load_email_widget(item, True)
            email_list = email_list.iloc[1:, :]
            if sys.platform != 'darwin':
                notification.notify(title=item['name'], message=item['title'], app_name="Mail", app_icon='resources/sender.ico')
        return email_list

    # load emails, input is the row of email
    def load_email_widget(self, email, insert_at_front=False):
        if insert_at_front:
            current_time = datetime.datetime.now().strftime(SHORT_TIME_FORMAT)
            self.current_emails.loc[self.current_emails.ID == email['ID'], 'time'] = current_time
            email['time'] = current_time
            self.log_incoming_email(email)
            self.set_unread_email_count()
            row_pos = 0
        else:
            row_pos = self.ui.emailList.rowCount()

        self.ui.emailList.insertRow(row_pos)
        cell1 = str(email['name']) + '<br>' + str(email['title'])
        self.set_cell(self.ui.emailList, row_pos, 0, cell1, QtGui.QFont("Calibri", 12, QtGui.QFont.Bold))
        self.set_cell(self.ui.emailList, row_pos, 1, str(email['time']), QtGui.QFont("Calibri", 10, QtGui.QFont.Bold))
        self.ui.emailList.item(row_pos, 1).setTextAlignment(Qt.AlignHCenter)
        self.ui.emailList.setRowHeight(row_pos, 65)
        self.change_row_background(row_pos, QtGui.QColor(245, 250, 255))

    def set_up_email_timestamp(self):
        random_numbers = [random.randint(1, 10) for _ in range(self.current_emails.shape[0] - 4)]

        # list sorted down from 10 to 1
        random_numbers.sort(reverse=True)
        current_day = datetime.date.today()
        time_list = []

        # set up the list of times for the emails (from oldest to newest)
        for i in random_numbers:
            time_list.append((current_day - datetime.timedelta(days=i)).strftime("%d %b"))

        time_list.append((datetime.datetime.now() - datetime.timedelta(hours=4, minutes=29)).strftime(SHORT_TIME_FORMAT))
        time_list.append((datetime.datetime.now() - datetime.timedelta(hours=3, minutes=15)).strftime(SHORT_TIME_FORMAT))
        time_list.append((datetime.datetime.now() - datetime.timedelta(hours=2, minutes=22)).strftime(SHORT_TIME_FORMAT))
        time_list.append((datetime.datetime.now() - datetime.timedelta(hours=0, minutes=17)).strftime(SHORT_TIME_FORMAT))

        for index, row in self.current_emails.iterrows():
            if time_list:
                self.current_emails.at[index, 'time'] = time_list.pop()
            else:
                self.current_emails.at[index, 'time'] = "-1"
            # del time_list[-1] #

    def change_row_background(self, row, colour):
        self.ui.emailList.item(row, 0).setBackground(colour)
        self.ui.emailList.item(row, 1).setBackground(colour)

    def get_current_email(self):
        current_row = self.ui.emailList.currentRow()
        email = self.ui.emailList.item(current_row, 0).text()
        subject_line = email.split('<br>')[1]

        return self.current_emails.loc[self.current_emails['title'] == subject_line].iloc[0]

    # ========================== sections ================================================

    def get_next_section(self):
        current_session_loc = self.session_list.index(self.current_session)
        print(current_session_loc)
        print(len(self.session_list))
        if len(self.session_list) > current_session_loc + 1:
            next_session = self.session_list[current_session_loc + 1]
            print(next_session)
            self.current_session = next_session
            self.setup_session()
        else:
            self.ui.close()

    def setup_primary_task(self):
        # read html file
        clear_layout(self.ui.primaryTaskL)
        self.primary_task = QtWebEngineWidgets.QWebEngineView()

        p_task_data = PrimaryTaskData(self)
        p_task_data.valueChanged.connect(self.get_task_data)

        self.channel = QtWebChannel.QWebChannel()
        self.channel.registerObject("data", p_task_data)

        self.primary_task.page().setWebChannel(self.channel)

        path = f"{os.getcwd()}/{self.get_current_session().get('primaryTaskHtml')}"
        self.primary_task.setUrl(QtCore.QUrl.fromLocalFile(path))

        self.ui.primaryTaskL.addWidget(self.primary_task)

    def save_primary_task_data_local(self):
        self.primary_task.page().runJavaScript(
            """
            tableToCSV();
            
        """
        )

    @QtCore.Slot(str)
    def get_task_data(self, value):
        print('....................')
        print(value)
        file_name = self.current_session + '_task.csv'
        path = os.path.join(self.folder_path, file_name)
        data = pd.DataFrame(columns=['category', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'])
        vlist = value.split('\n')
        for v in vlist:
            row = v.split('#$%')
            print(row)
            print(len(row))
            if len(row) == 2:
                row = row + ['', '', '', '', '']

            data.loc[len(data)] = row
        data.to_csv(str(path), index=False, header=False)

    # ========================= logging ==========================================

    def create_log_file(self):
        print('create log file')
        self.folder_path = os.path.join(self.save_location, self.username)
        Path(self.folder_path).mkdir(parents=True, exist_ok=True)
        self.file_name = os.path.join(self.folder_path, LAUNCH_TIME.strftime(f'{DATE_FORMAT}_{LONG_TIME_FORMAT}') + '_log.csv')

        # self.file_name = self.folder_path + LAUNCH_TIME.strftime(f'{DATE_FORMAT}_{LONG_TIME_FORMAT}') + '_log.csv'
        global LOG_FILE_NAME
        LOG_FILE_NAME = self.file_name
        print("logfile name")
        print(LOG_FILE_NAME)
        with open(self.file_name, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["time", "timestamp", "username", "ID", "email", "action", "detail", "studyCondition"])

    def log_email(self, action, detail=""):
        email = self.get_current_email()

        with open(self.file_name, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(
                [datetime.datetime.now(), time.time() * 1000, self.username, email['ID'], email['title'],
                 action, detail, self.get_current_session().get('name')])

    def log_incoming_email(self, email):
        with open(self.file_name, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(
                [datetime.datetime.now(), time.time() * 1000, self.username, email['ID'], email['title'],
                 "incoming email", "", self.get_current_session().get('name')])

    # ============================= Event table ====================================================

    def set_up_email_list_table(self):
        self.ui.emailList.setRowCount(0)
        self.ui.emailList.setColumnCount(2)

        self.ui.emailList.setHorizontalHeaderLabels(['Email', 'Time'])
        header = self.ui.emailList.horizontalHeader()
        # self.ui.emailList.setColumnWidth(0, 70)
        self.ui.emailList.setColumnWidth(1, 50)

        self.ui.emailList.setItemDelegateForColumn(0, ListDelegate())

        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)

        for i in range(0, self.current_emails.shape[0]):
            self.load_email_widget(self.current_emails.iloc[i])

        self.ui.emailList.selectRow(0)

        self.current_email = self.get_current_email()
        self.display_email()

    def email_table_clicked(self):
        self.display_email()
        self.log_email("email opened")

    @staticmethod
    def set_cell(table, row, column, value, style=None, merge_row=-1, merge_col=-1):
        if merge_row != -1:
            table.setSpan(row, column, merge_row, merge_col)
        new_item = QTableWidgetItem(value)
        if style is not None:
            new_item.setFont(style)
        table.setItem(row, column, new_item)

    def set_window(self, response_type):
        if response_type == "reply":
            self.respond_window = QUiLoader().load('resources/UI_files/reply.ui')
            self.respond_window.setWindowTitle("Reply")
        else:
            self.respond_window = QUiLoader().load('resources/UI_files/forward.ui')
            self.respond_window.setWindowTitle("Forward")

        self.respond_window.setWindowFlags(QtCore.Qt.WindowCloseButtonHint)
        self.respond_window.deleteBtn.clicked.connect(self.respond_window.reject)
        self.respond_window.sendBtn.clicked.connect(lambda: self.reply_send_btn_clicked(response_type))
        self.respond_window.show()

    def respond_btn_clicked(self, types):
        print('reply')
        current_email = self.get_current_email()

        # set up the sender, subject line etc.
        if types == 'reply':
            self.set_window("reply")
            self.respond_window.toText.setText(current_email['name'])
            self.respond_window.ccText.setHidden(True)
            self.respond_window.ccLine.setHidden(True)
            self.respond_window.ccLabel.setHidden(True)
            self.respond_window.subjectLine.setText('Re: ' + current_email['title'])
            self.respond_window.content.setFocus()
            self.log_email("reply button clicked")

        elif types == 'reply_to_all':
            self.set_window("reply")
            self.respond_window.toText.setText(current_email['name'])
            to_addresses = current_email['to'].split(', ')
            if 'me' in to_addresses:
                to_addresses.remove('me')
            self.respond_window.ccText.setText(', '.join(str(s) for s in to_addresses))
            self.respond_window.subjectLine.setText('Re: ' + current_email['title'])
            self.respond_window.content.setFocus()
            self.log_email("reply to all button clicked")
        else:
            self.set_window("forward")
            self.respond_window.subjectLine.setText('Forward: ' + current_email['title'])
            self.log_email("forward button clicked")

    def reply_send_btn_clicked(self, response_type):
        if response_type == "reply":
            if self.respond_window.content.toPlainText() == '':
                message_notification(self,
                                    "Please write something in the text field",
                                     False)
            else:
                #  log data
                self.log_email("reply", self.respond_window.content.toPlainText())
                self.respond_window.reject()
        else:
            if self.respond_window.toBox.toPlainText() == '':
                message_notification(self,
                                    "Please select where you want to forward the email",
                                     False)
            else:
                #  log data
                self.log_email(
                    "forward to " + self.respond_window.toBox.toPlainText(), self.respond_window.content.toPlainText())
                self.respond_window.reject()

    # ============================= email top bar buttons ==========================================

    def star_btn_clicked(self):
        current = self.get_current_email()
        index = self.current_emails.index[self.current_emails['ID'] == current['ID']].tolist()[0]

        # check star state and toggle it
        self.current_emails.at[index, 'star'] = not self.get_current_email()['star']
        self.log_email(f"email {'un' if self.get_current_email()['star'] else ''}star")

        self.set_email_row_font_colour(self.get_current_email())
        self.update_star(self.current_emails.at[index, 'star'])

    def update_star(self, value):
        self.ui.starBtn.setIcon(QtGui.QPixmap(f"resources/{'star_activate' if value else 'star'}.png"))

    def delete_btn_click(self):
        # self.send_popup('The email has been deleted', 3)
        self.log_email("email deleted")
        self.remove_current_selected_email()

    def report_btn_click(self):
        # self.send_popup('The email has been reported', 3)
        self.log_email("email reported")
        _ = self.get_current_email()
        # self.reported_emails = pd.concat([self.reported_emails, current_email.to_frame().T])

        self.remove_current_selected_email()
        message_notification(self, "You have reported the selected email", False)

    def remove_current_selected_email(self):
        # print(self.current_emails)
        current_email = self.get_current_email()
        self.current_emails.drop(
            self.current_emails.index[self.current_emails['ID'] == self.get_current_email()['ID']], inplace=True)
        print('--------------------------------')
        print(self.previous_emails)

        if self.previous_emails[-1] == current_email.title:
            self.previous_emails[:] = (x for x in self.previous_emails if x != self.previous_emails[-1])
        print()
        if len(self.previous_emails) != 0:
            previous_item = self.ui.emailList.findItems(self.previous_emails[-1], QtCore.Qt.MatchContains)
            print(previous_item)
            if len(previous_item) == 1:  # if the previous email exist in the email table
                print('previous exist')
                self.ui.emailList.removeRow(self.ui.emailList.currentRow())
                previous_row = self.ui.emailList.findItems(self.previous_emails[-1], QtCore.Qt.MatchContains)[0].row()
                self.ui.emailList.selectRow(previous_row)

                self.previous_emails[:] = (x for x in self.previous_emails if x != self.previous_emails[-1])
            else:
                print('previous not exist')
                self.ui.emailList.removeRow(self.ui.emailList.currentRow())
                self.ui.emailList.selectRow(self.ui.emailList.currentRow())
        else:
            print('no previous')
            self.ui.emailList.removeRow(self.ui.emailList.currentRow())
            self.ui.emailList.selectRow(self.ui.emailList.currentRow())

        print("vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv")

        self.display_email()

    def unread_btn_click(self):
        # self.send_popup('The email is marked unread', 3)
        item = self.get_current_email()
        self.current_emails.loc[self.current_emails['ID'] == item['ID'], 'readState'] = False
        self.set_unread_email_count()

        self.set_row_font(self.ui.emailList.currentRow(), QtGui.QFont.Bold)
        self.change_row_background(self.ui.emailList.currentRow(), QtGui.QColor(245, 250, 255))

        # logging
        self.log_email("email marked as unread")

    # =============================== display the email =============================================

    def display_email(self):
        self.previous_emails = self.previous_emails + [self.current_email.title]

        item = self.get_current_email()
        self.current_email = item

        self.current_emails.loc[self.current_emails['ID'] == item['ID'], 'readState'] = True
        self.set_unread_email_count()
        self.set_email_row_font_colour(item)

        # set subject line
        self.ui.emailSubjectLine.setText(item['title'])
        # set sender email address
        self.ui.fromAddress.setText(item['name'] + '  <' + item['from'] + '>')
        # set star state
        self.update_star(item['star'])
        # set to address
        self.ui.toAddress.setText('to ' + item['to'])

        self.setup_email_css(item['category']) if self.get_current_session().get('cssStyles') else self.reset_css()

        # set the content
        clear_layout(self.ui.contentL)
        web_engine_view = HtmlView(self)
        path = f"{os.getcwd()}/{self.config.get('emailResourceLocation')}/html/{item['content']}"
        print(path)
        web_engine_view.load(QtCore.QUrl().fromLocalFile(path))
        web_engine_view.resize(self.ui.contentW.width(), self.ui.contentW.height())
        self.ui.contentL.addWidget(web_engine_view)
        web_engine_view.page().linkHovered.connect(self.link_hovered)
        # web_engine_view.setZoomFactor(1.5)
        web_engine_view.show()

        # set the attachment
        clear_layout(self.ui.attachmentLayout)

        if item['attachment'] != 'None':
            attachment_string = item['attachment']
            attachments = attachment_string.split(',')
            for a in attachments:
                if a[:2] == 'P_':
                    btn = self.create_phish_attachment_btn(a[2:])
                else:
                    btn = self.create_attachment_btn(a)
                self.ui.attachmentLayout.addWidget(btn)

            space_item = QtWidgets.QSpacerItem(150, 10, QtWidgets.QSizePolicy.Expanding)
            self.ui.attachmentLayout.addSpacerItem(space_item)
        self.ui.replyToAllBtn.setHidden(item['to'] == 'me')

    def link_hovered(self, link):
        if not ((link == "") and (self.hovered_url == 'none')):
            self.hovered_url = link
            print(self.hovered_url)

            if self.hovered_url != "":
                self.log_email("url hovered", link)
                self.ui.URLDisplay.setHidden(False)
                # if link == "https://iam.auckland.ac.nz/profile/SAML2/Redirect/SSO?execution=e1s1":
                #     link = "https://docs.google.com/spreadsheets/d/1I32l2q-FAGXPPx32jT2HkrtD8yxNOU7KGrDNHb5-dxM/edit?usp=sharing"
                self.ui.URLDisplay.setText(link)
                print('hovered')
            else:
                self.log_email("url unhovered")
                self.hovered_url = 'none'
                self.ui.URLDisplay.setHidden(True)

                print('unhovered')

    def set_row_font(self, row, font, size=10):
        self.ui.emailList.item(row, 0).setFont(QtGui.QFont('Calibri', size + 2, font))
        self.ui.emailList.item(row, 1).setFont(QtGui.QFont('Calibri', size, font))

    def set_email_row_font_colour(self, row):
        if row['star']:
            self.set_row_font(self.ui.emailList.currentRow(), QtGui.QFont.Bold)
            self.change_row_background(self.ui.emailList.currentRow(), QtGui.QColor(235, 200, 200))
        else:
            self.set_row_font(self.ui.emailList.currentRow(), QtGui.QFont.Normal)
            self.change_row_background(self.ui.emailList.currentRow(), QtGui.QColor(245, 250, 255))

    def set_unread_email_count(self):
        self.ui.unreadEmailCount.setText(str(len(self.current_emails) - (self.current_emails['readState'].convert_dtypes(convert_boolean=True)).sum()))

    def setup_email_css(self, category):
        self.ui.emailSubjectLine.setStyleSheet(self.get_current_session().get('cssStyles').get(category).get('header'))
        self.ui.fromAddress.setStyleSheet(self.get_current_session().get('cssStyles').get(category).get('sender'))
        self.ui.contentW.setStyleSheet(self.get_current_session().get('cssStyles').get(category).get('body'))

        if self.get_current_session().get('cssStyles').get(category).get('headerIcon') == '':
            self.ui.subjectIcon.hide()
        else:
            self.ui.subjectIcon.show()
            self.ui.subjectIcon.setStyleSheet(self.get_current_session().get('cssStyles').get(category).get('headerIcon'))

        if self.get_current_session().get('cssStyles').get(category).get('senderIcon') == '':
            self.ui.userIcon.setStyleSheet(
                'border:None; border-image: url(resources/sender.png) 0 0 0 0 stretch stretch;')
        else:
            self.ui.userIcon.setStyleSheet(
                self.get_current_session().get('cssStyles').get(category).get('senderIcon'))

    def reset_css(self):
        self.ui.emailSubjectLine.setStyleSheet('')
        self.ui.subjectIcon.hide()
        self.ui.fromAddress.setStyleSheet('')
        self.ui.userIcon.setStyleSheet(
            'border:None; border-image: url(resources/sender.png) 0 0 0 0 stretch stretch;')
        self.ui.contentW.setStyleSheet('')

    # ================================== attachment ======================================

    # ===== legit attachment =====
    def create_attachment_btn(self, name):
        btn = QtWidgets.QPushButton(name)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(os.path.abspath(os.getcwd()) + r'/resources/attachment.png'))
        btn.setIcon(icon)
        btn.setStyleSheet(
            "border: 1px solid rgb(150, 150, 150); border-radius:2px; background:#56d5f9; margin: 10px; font-size: 18px; padding: 5px;")
        btn.clicked.connect(lambda: self.open_attachment(name))
        return btn

    def open_attachment(self, name):
        attachment_root = f"{os.getcwd()}/{self.config.get('emailResourceLocation')}/Attachments"
        webbrowser.open(attachment_root + '/' + name)
        self.log_email("open attachment", "legit attachment: " + name)

    # ===== phishing attachment =====
    def create_phish_attachment_btn(self, name):
        btn = QtWidgets.QPushButton(name)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(os.path.abspath(os.getcwd()) + r'/resources/attachment.png'))
        btn.setIcon(icon)
        btn.setStyleSheet(
            "border: 1px solid rgb(150, 150, 150); border-radius:2px; background:#56d5f9; margin: 10px; font-size: 18px; padding: 5px;")
        btn.clicked.connect(lambda: self.phish_attachment_clicked(name))
        return btn

    def phish_attachment_clicked(self, name):
        title = name.split('.', 1)[0]
        win1 = QtWidgets.QWidget()
        win1.adjustSize()
        # screen_resolution = app.desktop().screenGeometry()
        win1.setGeometry(100, 100, 800 // 2, 600 // 2, )
        win1.setWindowTitle(title)
        time.sleep(1)
        win1.show()
        time.sleep(1.5)
        file_not_opened_warning(name)

        self.log_email("open attachment", "phishing attachment: " + name)


# ================================ Utils =======================================

def clear_layout(layout):
    if layout is not None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()
            elif child.layout() is not None:
                clear_layout(child.layout())


def file_not_opened_warning(filename):
    print('warning')
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Warning)
    msg_box.setText(
        "Could not open file: " + filename + ". Something unexpected happened during the execution. \nError code: 506")
    msg_box.setWindowTitle("Windows")
    msg_box.setStandardButtons(QMessageBox.Ok)

    return_value = msg_box.exec()
    if return_value == QMessageBox.Ok:
        print('OK clicked')


def message_notification(context, text, new_section=True):
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setText(text)
    msg_box.setWindowTitle("Notification")
    msg_box.setStandardButtons(QMessageBox.Ok)

    return_value = msg_box.exec()
    if (return_value == QMessageBox.Ok) and new_section:
        print('OK clicked')
        context.get_next_section()


# Function to insert row in the dataframe
def insert_row_(row_number, df, row_value):
    # Slice the upper half of the dataframe
    df1 = df[0:row_number]
    # Store the result of lower half of the dataframe
    df2 = df[row_number:]
    # Insert the row in the upper half dataframe
    df1 = pd.concat([df1, row_value])
    # Concat the two dataframes
    df_result = pd.concat([df1, df2])
    # Reassign the index labels
    df_result.index = pd.Index(data=[*range(df_result.shape[0])])
    # Return the updated dataframe
    return df_result


class EmailContentPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, _type, is_main_frame):
        if _type == QWebEnginePage.NavigationTypeLinkClicked:
            QtGui.QDesktopServices.openUrl(url)
            log = pd.read_csv(LOG_FILE_NAME)
            row = log.iloc[-1]
            with open(LOG_FILE_NAME, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(
                    [datetime.datetime.now(), time.time() * 1000, row[2], row[3], row[4],
                     'link clicked', url.toString(), row[7]])
            return False
        return True


class HtmlView(QWebEngineView):
    def __init__(self, *args, **kwargs):
        QWebEngineView.__init__(self, *args, **kwargs)
        self.setPage(EmailContentPage(self))


class PrimaryTaskData(QtCore.QObject):
    valueChanged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = ""

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = v
        self.valueChanged.emit(v)


class ListDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        painter.save()
        doc = QTextDocument()
        doc.setHtml(opt.text)
        doc.setDefaultFont(opt.font)
        opt.text = ""
        style = opt.widget.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter)
        painter.translate(opt.rect.left(), opt.rect.top())
        clip = QRectF(0, 0, opt.rect.width(), opt.rect.height())
        doc.drawContents(painter, clip)
        painter.restore()

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = QTextDocument()
        doc.setHtml(opt.text)
        doc.setTextWidth(opt.rect.width())
        return QSize(doc.idealWidth(), int(doc.size().height()))
