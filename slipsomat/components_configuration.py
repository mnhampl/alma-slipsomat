from __future__ import print_function

import os
import os.path
import re
import time
import sys

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.errorhandler import NoSuchElementException
from colorama import Fore, Back, Style

from .slipsomat import LetterContent

class ComponentsConfiguration(object):
    """Interface to "Customize letters" in Alma."""

    css_selector_table          = '#filesAndLabels'
    css_selector_table_row      = '.jsRecordContainer'
    css_selector_col_name       = '#SELENIUM_ID_filesAndLabels_ROW_%d_COL_letterXslcfgFilefilename'
    css_selector_col_customized = '#SELENIUM_ID_filesAndLabels_ROW_%d_COL_customized' 


    def __init__(self, worker):
        self.filenames = []
        self.update_dates = []
        self.worker = worker
#         self.open()
#         self.read()

    def open(self):
        """Go from Alma start page to general configuration and open subpage"""
        linkname = 'Components Configuration'
        
        try:
            # at page that lists letters?
            self.worker.first(By.CSS_SELECTOR, self.css_selector_table)
        except NoSuchElementException:
            # not at page that lists letters?
            self.print_letter_status('Opening table...', '')

            # Goto Alma start page
            self.worker.goto_alma_start_page()
            
            # Open Alma configuration
            self.worker.wait_for_and_click(By.CSS_SELECTOR, '#ALMA_MENU_TOP_NAV_configuration')
            
            # Open configuration "General" 
            self.worker.click(By.XPATH, '//*[@href="#CONF_MENU6"]')
            
            # Open Subpage
            self.worker.click(By.XPATH, '//*[text() = "' + linkname + '"]')
            self.worker.wait_for(By.CSS_SELECTOR, self.css_selector_table)

        return self

    def modified(self, filename):
#         idx = self.filenames.index(filename)
#         return self.update_dates[idx]
        return ""

    def set_modified(self, filename, date):
        # Allow updating a single date instead of having to re-read the whole table
        idx = self.filenames.index(filename)
        self.update_dates[idx] = date

    def print_letter_status(self, filename, msg, progress=None, newline=False):
        sys.stdout.write('\r{:100}'.format(''))  # We clear the line first
        if progress is not None:
            sys.stdout.write('\r[{}] {:60} {}'.format(
                progress,
                filename.split('/')[-1],
                msg
            ))
        else:
            sys.stdout.write('\r{:60} {}'.format(
                filename.split('/')[-1],
                msg
            ))
        if newline:
            sys.stdout.write('\n')
        sys.stdout.flush()


    def read(self):
        self.filenames = []

        # number of letters on page 
        elems_rows = self.worker.all(By.CSS_SELECTOR, self.css_selector_table_row)
        
        # first try: only read the first page
        for i in range(0, len(elems_rows)):
            lettername = self.worker.all(By.CSS_SELECTOR, self.css_selector_col_name % i)[0].text
            
            self.filenames.append(lettername)
            print(str(i+1) + ': ' + lettername)
        

#         # Read the modification date column
#         elems = self.worker.all(By.CSS_SELECTOR,
#                                 '#lettersOnPage tr > td:nth-child(%d) > span' % updatedate_col)
#         self.update_dates = [el.text for el in elems]
# 
#         # return [{x[0]:2 {'modified': x[1], 'index': n}} for n, x in enumerate(zip(filenames, update_dates))]


    def is_customized(self, filename):
        index = self.filenames.index(filename)
        css_selector_element = self.css_selector_col_customized % index
        
        self.worker.wait_for(By.CSS_SELECTOR, css_selector_element)
        updated_by = self.worker.first(By.CSS_SELECTOR, css_selector_element)

        return updated_by.text not in ('-', 'Network')

    def assert_filename(self, filename):
        # Assert that we are at the right letter
        self.worker.wait_for(By.ID, 'breadcrumbs')
        
        element = self.worker.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.pageTitle'))
        )
        
        elt = element.text
        assert elt == filename, "%r != %r" % (elt, filename)

    def open_letter(self, filename):
        self.open()

        # Open a letter and return its contents as a LetterContent object.
        index = self.filenames.index(filename)
        self.worker.wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, self.css_selector_col_name % index))
        )

        time.sleep(0.2)

        # Open Letter configuration
        self.worker.scroll_into_view_and_click((self.css_selector_col_name + ' a') % index, By.CSS_SELECTOR)
        time.sleep(0.2)

        # We should now be at the letter edit form. Assert that filename is indeed correct
        self.assert_filename(filename)


        # goto tab "Template"
        # Click tab "Template" menu item
        css_selector_button_template = '#cnew_letter_labeltemplate_span a'
        self.worker.wait_for(By.CSS_SELECTOR, css_selector_button_template)
        self.worker.scroll_into_view_and_click(css_selector_button_template, By.CSS_SELECTOR)
        

#         if self.is_customized(filename):
#             # Click "Edit" menu item
#             edit_btn_selector = '#ROW_ACTION_fileList_{}_c\\.ui\\.table\\.btn\\.edit a'.format(index)
#             self.worker.scroll_into_view_and_click(edit_btn_selector, By.CSS_SELECTOR)
#         else:
#             # Click "Customize" menu item
#             customize_btn_selector = '#ROW_ACTION_fileList_{} a'.format(index)
#             self.worker.scroll_into_view_and_click(customize_btn_selector, By.CSS_SELECTOR)
# 
#             element = self.worker.wait_for(
#                 By.CSS_SELECTOR,
#                 '#PAGE_BUTTONS_cbuttonconfirmationconfirm, #pageBeanfileContent'
#             )
#             if element.get_attribute("id") == 'PAGE_BUTTONS_cbuttonconfirmationconfirm':
#                 # If this is the first time the letter is edited, and it's managed in network zone,
#                 # we will get a modal dialog asking us to confirm if we want to edit it.
#                 #
#                 # > This row is managed in the Network. If customized, no future updates will be
#                 # > retrieved from the Network for this row. Are you sure you want to proceed?
#                 #
#                 element.click()



        css_selector_template_textarea = 'pageBeanfileContent'
        self.worker.wait_for(By.ID, css_selector_template_textarea)
        txtarea = self.worker.first(By.ID, css_selector_template_textarea)
        return LetterContent(txtarea.text)


    def close_letter(self):
        # If we are at specific letter, press the "Cancel" button.
        elems = self.worker.all(By.CSS_SELECTOR, '.pageTitle')
        if len(elems) != 0:
            btn_selector = '#PAGE_BUTTONS_cbuttonnavigationcancel'
            self.worker.scroll_into_view_and_click(btn_selector, By.CSS_SELECTOR)

        
        
#         # If we are at specific letter, press the "go back" button.
#         elems = self.worker.all(By.CSS_SELECTOR, '.pageTitle')
#         if len(elems) != 0:
#             title = elems[0].text.strip()
#             if title == 'Configuration File':
#                 try:
#                     backBtn = self.worker.first(By.ID, 'PAGE_BUTTONS_cbuttonback')
#                     backBtn.click()
#                 except NoSuchElementException:
#                     pass
#                 try:
#                     backBtn = self.worker.first(By.ID, 'PAGE_BUTTONS_cbuttonnavigationcancel')
#                     backBtn.click()
#                 except NoSuchElementException:
#                     pass
# 
#             self.worker.wait_for(By.CSS_SELECTOR, '#lettersOnPage')

    def put_contents(self, filename, content):
        """
        Save letter contents to Alma.

        This method assumes the letter has already been opened.
        """
        self.assert_filename(filename)

        # The "normal" way to set the value of a textarea with Selenium is to use
        # send_keys(), but it took > 30 seconds for some of the larger letters.
        # So here's a much faster way:
        txtarea = self.worker.first(By.ID, 'pageBeanfileContent')
        txtarea_id = txtarea.get_attribute('id')

        value = content.text.replace('"', '\\"').replace('\n', '\\n')
        script = 'document.getElementById("%s").value = "%s";' % (txtarea_id, value)
        self.worker.driver.execute_script(script)

        # Submit the form
        try:
            btn = self.worker.first(By.ID, 'PAGE_BUTTONS_cbuttonsave')
        except NoSuchElementException:
            btn = self.worker.first(By.ID, 'PAGE_BUTTONS_cbuttoncustomize')
        btn.click()

        # Wait for the table view.
        # Longer timeout per https://github.com/scriptotek/alma-slipsomat/issues/33
        self.worker.wait_for(By.CSS_SELECTOR, '.typeD table', timeout=40)

        return True


    def pull(self, local_storage, status_file):

        count_new = 0
        count_changed = 0

        self.open()
        self.read()

        for idx, filename in enumerate(self.filenames):
            progress = '%3d/%3d' % ((idx + 1), len(self.filenames))
    
            self.print_letter_status(filename, '', progress)
    
            self.print_letter_status(filename, 'checking...', progress)
            try:
                content = self.open_letter(filename)
                # if self.is_customized(filename):
                #     content = self.open_letter(filename)
                # else:
                #     content = self.open_default_letter(filename)
            except TimeoutException:
                # Retry once
                self.print_letter_status(filename, 'retrying...', progress)
                if self.is_customized(filename):
                    content = self.open_letter(filename)
                else:
                    content = self.open_default_letter(filename)
    
            self.close_letter()
    
            old_sha1 = status_file.checksum(filename)
            if content.sha1 == old_sha1:
                self.print_letter_status(filename, 'no changes', progress, True)
                continue
    
            # Store letter and update status.json
    #         if not local_storage.store(filename, content, self.modified(filename)):
    #             self.print_letter_status(
    #                 filename, Fore.RED + 'skipped due to conflict' + Style.RESET_ALL, progress, True)
    #             continue
            if not local_storage.store(filename, content, self.modified(filename)):
                self.print_letter_status(
                    filename, Fore.RED + 'skipped due to conflict' + Style.RESET_ALL, progress, True)
                continue
    
            if old_sha1 is None:
                count_new += 1
                self.print_letter_status(filename, Fore.GREEN + 'fetched new letter @ {}'.format(
                    content.sha1[0:7]) + Style.RESET_ALL, progress, True)
            else:
                count_changed += 1
                self.print_letter_status(filename, Fore.GREEN + 'updated from {} to {}'.format(
                    old_sha1[0:7], content.sha1[0:7]) + Style.RESET_ALL, progress, True)
    
        sys.stdout.write(Fore.GREEN + 'Fetched {} new, {} changed letters\n'.format(
            count_new, count_changed) + Style.RESET_ALL)
    
