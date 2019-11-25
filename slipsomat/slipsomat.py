# encoding=utf8
from __future__ import print_function

import os
import os.path
import re
import time
import sys
import hashlib
import json
import difflib
import tempfile

from datetime import datetime
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.errorhandler import NoSuchElementException
from xml.etree import ElementTree
from colorama import Fore, Back, Style

try:
    input = raw_input  # Python 2
except NameError:
    pass  # Python 3


def normalize_line_endings(text):
    # Normalize line endings to LF and strip ending linebreak.
    # Useful when collaborating cross-platform.
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


def color_diff(diff):
    for line in diff:
        if line.startswith('+'):
            yield Fore.GREEN + line + Fore.RESET
        elif line.startswith('-'):
            yield Fore.RED + line + Fore.RESET
        elif line.startswith('^'):
            yield Fore.BLUE + line + Fore.RESET
        else:
            yield line


def resolve_conflict(filename, local_content, remote_content, msg):
    print()
    print(
        '\n' + Back.RED + Fore.WHITE + '\n\n  Conflict: ' + msg + '\n' + Style.RESET_ALL
    )

    msg = 'Continue with {}?'.format(filename)
    while True:
        response = input(Fore.CYAN + "%s [y: yes, n: no, d: diff] " % msg + Style.RESET_ALL).lower()[:1]
        if response == 'd':
            show_diff(remote_content, local_content)
        else:
            return response == 'y'


def show_diff(dst, src):
    src = src.text.strip().splitlines()
    dst = dst.text.strip().splitlines()

    print()
    for line in color_diff(difflib.unified_diff(dst, src, fromfile='Alma', tofile='Local')):
        print(line)


class LetterContent(object):

    def __init__(self, text, filename=None):
        self.text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
        self.filename = filename
        self.validate()

    @property
    def sha1(self):
        m = hashlib.sha1()
        m.update(self.text.encode('utf-8'))
        return m.hexdigest()

    def validate(self):
        if self.text == '':
            return
        try:
            ElementTree.fromstring(self.text)
        except ElementTree.ParseError as e:
            print('%sError: %s contains invalid XML:%s' % (Fore.RED, self.filename or 'The letter', Style.RESET_ALL))
            print(Fore.RED + str(e) + Style.RESET_ALL)
            return


class LocalStorage(object):
    """File storage abstraction class."""

    def __init__(self, status_file):
        self.status_file = status_file

    def is_modified(self, filename):
        """Return True if the letter has local changes not yet pushed to Alma."""
        local_content = self.get_content(filename)
        return local_content.text != '' and local_content.sha1 != self.status_file.checksum(filename)

    def get_content(self, filename):
        """
        Read the contents of a letter from disk and return it as a LetterContent object.

        If no local version exists yet, an empty LetterContent object is returned.
        """
        if not os.path.isfile(filename):
            return LetterContent('', filename=filename)
        with open(filename, 'rb') as fp:
            return LetterContent(fp.read().decode('utf-8'), filename=filename)

    def store(self, letter_info, content, modified):
        """
        Store the contents of a letter to disk.

        The method first checks if the local version has changes that will be overwritten.
        """
        
        # The page Letters Configuration does not show the filenames but letter names
        # there is no possibility to find out the filenames that are used internally
        # however, the user is (mostly) confronted with the letter names anyway 
        filename = letter_info.get_filename() 
        
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))

        local_content = self.get_content(filename)
        if local_content.text != '' and local_content.sha1 != self.status_file.checksum(letter_info.unique_name):
            # The local file has been changed
            if not resolve_conflict(filename, content, local_content,
                                    'Pulling in this file would cause local changes to be overwritten.'):
                return False

        # Actually store the contents to disk
        with open(filename, 'wb') as f:
            f.write(content.text.encode('utf-8'))

        # Update the status file
        self.status_file.set_checksum(letter_info.get_filename(), content.sha1)
        self.status_file.set_modified(letter_info.get_filename(), modified)

        return True

    def store_default(self, filename, content):
        """
        Store the contents of a default letter to disk.

        Since the default letters cannot be uploaded, only downloaded, we do not care to check
        if the local file has changes that will be overwritten.
        """
        defaults_filename = os.path.join('defaults', filename)
        if not os.path.exists(os.path.dirname(defaults_filename)):
            os.makedirs(os.path.dirname(defaults_filename))
        with open(defaults_filename, 'wb') as f:
            f.write(content.text.encode('utf-8'))

        # Update the status file
        self.status_file.set_default_checksum(filename, content.sha1)


class StatusFile(object):

    def __init__(self):
        letters = {}
        if os.path.exists('status.json'):
            with open('status.json') as fp:
                contents = json.load(fp)
            letters = contents['letters']

        self.letters = letters

    def save(self):
        data = {
            'version': 1,
            'letters': self.letters,
        }
        jsondump = json.dumps(data, sort_keys=True, indent=2)

        # Remove trailling spaces (https://bugs.python.org/issue16333)
        jsondump = re.sub(r'\s+$', '', jsondump, flags=re.MULTILINE)

        # Normalize to unix line endings
        jsondump = normalize_line_endings(jsondump)

        with open('status.json', 'wb') as fp:
            fp.write(jsondump.encode('utf-8'))

    def get(self, filename, property, default=None):
        if filename not in self.letters:
            return default
        return self.letters[filename].get(property)

    def set(self, filename, property, value):
        if filename not in self.letters:
            self.letters[filename] = {}
        self.letters[filename][property] = value
        self.save()

    def modified(self, filename):
        return self.get(filename, 'modified')

    def checksum(self, filename):
        return self.get(filename, 'checksum')

    def default_checksum(self, filename):
        return self.get(filename, 'default_checksum')

    def set_modified(self, filename, modified=None):
        if modified is None:
            modified = datetime.now().strftime('%d/%m/%Y')
        self.set(filename, 'modified', modified)

    def set_checksum(self, filename, checksum):
        self.set(filename, 'checksum', checksum)

    def set_default_checksum(self, filename, checksum):
        self.set(filename, 'default_checksum', checksum)



# Commands ---------------------------------------------------------------------------------

def pull_defaults(table, local_storage, status_file):
    """
    Update the local copies of the default versions of the Alma letters.

    This command downloads the latest version of all the default versions of the Alma letters.
    If you keep the folder under version control, this allows you to detect changes in the
    default letters. Unfortunately, there is no way of knowing if a default letter has changed
    without actually opening it, so we have to open each and every letter. This takes some time
    of course.

    Params:
        table: TemplateConfigurationTable object
        local_storage: LocalStorage object
        status_file: StatusFile object
    """
    count_new = 0
    count_changed = 0
    for idx, filename in enumerate(table.filenames):
        progress = '%d/%d' % ((idx + 1), len(table.filenames))
        table.print_letter_status(filename, 'checking...', progress)
        try:
            content = table.open_default_letter(filename)
        except TimeoutException:
            # Retry once
            table.print_letter_status(filename, 'retrying...', progress)
            content = table.open_default_letter(filename)

        table.print_letter_status(filename, 'closing...', progress)
        table.close_letter()

        old_sha1 = status_file.default_checksum(filename)

        if content.sha1 == old_sha1:
            table.print_letter_status(filename, 'no changes', progress, True)
            continue

        # Write contents to default letter
        local_storage.store_default(filename, content)

        if old_sha1 is None:
            count_new += 1
            table.print_letter_status(filename, Fore.GREEN + 'fetched new letter @ {}'.format(
                content.sha1[0:7]) + Style.RESET_ALL, progress, True)
        else:
            count_changed += 1
            if old_sha1 == content.sha1:
                table.print_letter_status(
                    filename, Fore.GREEN + 'no changes' + Style.RESET_ALL, progress, True)
            else:
                table.print_letter_status(filename, Fore.GREEN + 'updated from {} to {}'.format(
                    old_sha1[0:7], content.sha1[0:7]) + Style.RESET_ALL, progress, True)

    sys.stdout.write(Fore.GREEN + 'Fetched {} new, {} changed default letters\n'.format(
        count_new, count_changed) + Style.RESET_ALL)


class TestPage(object):
    """Interface to "Notification Template" in Alma."""

    def __init__(self, worker):
        self.worker = worker

    def open(self):
        try:
            self.worker.first(By.ID, 'cbuttonupload')
        except NoSuchElementException:
            self.worker.get('/mng/action/home.do')

            # Open Alma configuration
            self.worker.wait_for_and_click(By.CSS_SELECTOR, '#ALMA_MENU_TOP_NAV_configuration')
            self.worker.click(By.XPATH, '//*[@href="#CONF_MENU6"]')  # text() = "General"
            self.worker.click(By.XPATH, '//*[text() = "Notification Template"]')

            self.worker.wait_for(By.ID, 'cbuttonupload')

    def test(self, filename, lang):

        self.open()
        wait = self.worker.waiter()

        if not os.path.isfile(filename):
            print('%sERROR: File not found: %s%s' % (Fore.RED, filename, Fore.RESET))
            return

        file_root, file_ext = os.path.splitext(filename)

        png_path = '%s_%s.png' % (file_root, lang)
        html_path = '%s_%s.html' % (file_root, lang)

        tmp = tempfile.NamedTemporaryFile('wb')
        with open(filename, 'rb') as fp:
            tmp.write(re.sub('<preferred_language>[a-z]+</preferred_language>',
                             '<preferred_language>%s</preferred_language>' % lang,
                             fp.read().decode('utf-8')).encode('utf-8'))
        tmp.flush()

        # Set language
        element = self.worker.first(By.ID, 'pageBeanuserPreferredLanguage')
        element.click()
        element = self.worker.first(By.ID, 'pageBeanuserPreferredLanguage_hiddenSelect')
        select = Select(element)
        opts = {el.get_attribute('value'): el.get_attribute('innerText') for el in select.options}
        if lang not in opts:
            print('%sERROR: Language not found: %s%s' % (Fore.RED, lang, Fore.RESET))
            return

        longLangName = opts[lang]

        element = wait.until(EC.element_to_be_clickable(
            (By.XPATH,
             '//ul[@id="pageBeanuserPreferredLanguage_hiddenSelect_list"]/li[@title="%s"]/a' % longLangName)
        ))
        element.click()

        # Upload the XML
        file_field = self.worker.first(By.ID, 'pageBeannewFormFile')
        file_field.send_keys(tmp.name)

        upload_btn = self.worker.first(By.ID, 'cbuttonupload')
        upload_btn.click()

        self.worker.wait_for(By.CSS_SELECTOR, '.infoErrorMessages')

        run_btn = wait.until(
            EC.element_to_be_clickable(
                (By.ID, 'PAGE_BUTTONS_admconfigure_notification_templaterun_xsl'))
        )

        cwh = self.worker.driver.current_window_handle

        run_btn.click()
        time.sleep(1)

        # Take a screenshot
        self.worker.driver.switch_to_window(self.worker.driver.window_handles[-1])

        if self.worker.driver.page_source.startswith('<xsl'):
            # Wrong window, try next one
            self.worker.driver.switch_to_window(self.worker.driver.window_handles[-2])

        # GitHub: #30  -> if 'beanContentParam=htmlContent' in self.worker.driver.current_url:
        self.worker.driver.set_window_size(
            self.worker.config.get('screenshot', 'width'),
            600
        )
        with open(html_path, 'w+b') as html_file:
            html_file.write(self.worker.driver.page_source.encode('utf-8'))
        print('Saved output: %s' % html_path)
        if self.worker.driver.save_screenshot(png_path):
            print('Saved screenshot: %s' % png_path)
        else:
            print('Failed to save screenshot')

        # if not found_win:
        #     print(Fore.RED + 'ERROR: Failed to produce output!' + Fore.RESET)
        self.worker.driver.switch_to_window(cwh)
        tmp.close()


def pull(letters_configuration, components_configuration, local_storage, status_file):
    """
    Update the local files with changes made in Alma.
 
    This will download letters whose remote checksum does not match the value in status.json.
 
    Params:
        letters_configuration:    
        components_configuration: 
        local_storage:            LocalStorage object
        status_file:              StatusFile object
    """
    components_configuration.pull(local_storage, status_file)
    letters_configuration.pull(local_storage, status_file)


def push(table, local_storage, status_file, files=None):
    """
    Push local changes to Alma.

    This will upload files that have been modified locally to Alma.

    Params:
        table: TemplateConfigurationTable object
        local_storage: LocalStorage object
        status_file: StatusFile object
        files: list of filenames. If None, all files that have changed will be pushed.
    """
    files = files or []
    if len(files) == 0:
        # If no files were specified, we will look for files that have changes.
        for filename in table.filenames:
            if local_storage.is_modified(filename):
                files.append(filename)

        if len(files) == 0:
            sys.stdout.write(
                Fore.GREEN + 'Found no modified files.' + Style.RESET_ALL + '\n')
            return

        sys.stdout.write(
            Fore.GREEN + 'Found {} modified file(s):'.format(len(files)) + Style.RESET_ALL + '\n')
        for filename in files:
            print(' - {}'.format(filename.replace('xsl/letters/', '')))

        msg = 'Push the file(s) to Alma? '
        if input("%s (y/N) " % msg).lower() != 'y':
            print('Aborting')
            return

    count_pushed = 0
    for idx, filename in enumerate(files):
        progress = '%d/%d' % ((idx + 1), len(files))
        if filename not in table.filenames:
            table.print_letter_status(filename, Fore.RED + 'File not found' + Style.RESET_ALL, progress, True)
            continue

        table.print_letter_status(filename, 'pushing', progress)
        old_sha1 = status_file.checksum(filename)

        local_content = local_storage.get_content(filename)
        remote_content = table.open_letter(filename)

        # Read text area content
        if remote_content.sha1 != old_sha1:
            msg = 'The remote version has changed. Overwrite remote version?'
            if not resolve_conflict(filename, local_content, remote_content, msg):
                table.print_letter_status(filename, 'skipped', progress, True)

                # Go back
                table.close_letter()

                # Skip to next letter
                continue

        table.put_contents(filename, local_content)
        count_pushed += 1
        msg = 'updated from {} to {}'.format(
            old_sha1[0:7], local_content.sha1[0:7])
        table.print_letter_status(filename, msg, progress, True)

        # Update the status file
        status_file.set_checksum(filename, local_content.sha1)
        status_file.set_modified(filename)

    sys.stdout.write(
        Fore.GREEN + 'Pushed {} file(s)\n'.format(count_pushed) + Style.RESET_ALL)


def test(testpage, files, languages):
    """
    Test the output of an XML file by running a "notification template" test in Alma.

    Params:
        worker: worker object
        files: list of XML files in test-data to use
        languages: list og languages to test
    """
    testpage.open()

    for n, filename in enumerate(files):
        for m, lang in enumerate(languages):
            cur = n * len(languages) + m + 1
            tot = len(languages) * len(files)
            print('[%d/%d] Testing "%s" using language "%s"' % (cur, tot,
                                                                os.path.basename(filename),
                                                                lang))

            testpage.test(filename, lang)
