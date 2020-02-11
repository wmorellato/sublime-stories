import os
import re
import os.path as path
import sublime
import sublime_plugin
import time
import threading
from datetime import date

HEADER_WIDTH = 85
MAX_HEADER = 2048
settings = None

# constants (I need to move some of this to the settings file)
DRAFTS_DIR = 'originais'
DRAFT = 'Original'

REVISIONS_DIR = 'revisoes'
REVISION = 'Revisão'

TEXT_REGION_BEGIN = 'INICIO'
TEXT_REGION_END = 'FIM'

PENDING = 'Pendente'
REVISED = 'Revisado'

# --------------------------------------------
# General functions
# --------------------------------------------

def plugin_loaded():
    global settings
    settings = sublime.load_settings("stories.sublime-settings")


def show_async(view, region):
    """
    Wait for a view to load and then update the
    visible area
    """
    while view.is_loading():
        time.sleep(0.1)

    view.show(region)


class Manager:
    """
    Manager all shorts and directories
    """

    def __init__(self):
        # setting dirs
        self.stories_root = settings.get('stories_root_path')

        if self.stories_root is None:
            sublime.message_dialog('Could not find the root directory for stories')
            return

        # orig dir name
        orig_dir_name = settings.get('original_dir_name', DRAFTS_DIR)
        self.orig_dir = path.join(self.stories_root, orig_dir_name)

        # revision dir name
        rev_dir_name = settings.get('revisions_dir_name', REVISIONS_DIR)
        self.rev_dir = path.join(self.stories_root, rev_dir_name)
        self.story_number = len(os.listdir(self.orig_dir))


    def create_original(self, title):
        """
        Create original file

        Returns:
            [str] -- path of the new story
        """
        file_path = path.join(self.orig_dir, '%d. %s.txt' % (self.story_number, title))

        with open(file_path, 'w') as f:
            f.write(Story.new_header(title, DRAFT, settings.get('author')))
            f.write('%s\n\n\n\n%s' % (TEXT_REGION_BEGIN, TEXT_REGION_END))

        return file_path


    def create_revision(self, title):
        """
        Create revision file

        Returns:
            [str] -- path of the new story
        """
        file_path = path.join(self.rev_dir, '%d. %s.txt' % (self.story_number, title))

        with open(file_path, 'w') as f:
            f.write(Story.new_header(title, REVISION, settings.get('author')))
            f.write('%s\n\n\n\n%s' % (TEXT_REGION_BEGIN, TEXT_REGION_END))

        return file_path


    def get_all_pending_for_revision(self):
        """
        Return pending shorts for revision

        Returns:
            [list] -- list with Story objects
        """
        if not self.stories_root:
            return []

        pending = []
        rev_path = path.join(self.stories_root, settings.get('revisions_dir_name'))
        rev_stories = os.listdir(rev_path)

        for sf in rev_stories:
            full_path = os.path.join(rev_path, sf)
            story = Story.from_file(full_path, False)

            if not story:
                continue

            if story.status == PENDING:
                pending.append(story)

        return pending


    def get_all_revised(self):
        """
        Return shorts already revised and ready for translation/publication

        Returns:
            [list] -- list with Story objects
        """
        if not self.stories_root:
            return []

        revised = []
        rev_path = path.join(self.stories_root, settings.get('revisions_dir_name'))
        rev_stories = os.listdir(rev_path)

        for sf in rev_stories:
            full_path = os.path.join(rev_path, sf)
            story = Story.from_file(full_path, False)

            if not story:
                continue

            if story.status == REVISED:
                revised.append(story)

        return revised


    def update_file_names(self, old_name, new_name):
        """
        Rename the files for both original and revision versions
        """        

        if not self.stories_root:
            return

        rev_path = path.join(self.stories_root, settings.get('revisions_dir_name'))
        ori_path = path.join(self.stories_root, settings.get('original_dir_name'))

        os.rename(path.join(rev_path, old_name), path.join(rev_path, new_name))
        os.rename(path.join(ori_path, old_name), path.join(ori_path, new_name))


    def open_story_files(self, orig_story_path, rev_story_path = None):
        """
        Open the story files (THE VIEW WILL STILL BE LOADING)

        Returns:
            [list] -- list with the views
        """
        views = []

        if not self.stories_root:
            return

        if rev_story_path:
            rev_path = path.join(self.stories_root, settings.get('revisions_dir_name'))
            rev_view = sublime.active_window().open_file(path.join(rev_path, rev_story_path))
            views.append(rev_view)

        orig_path = path.join(self.stories_root, settings.get('original_dir_name'))
        orig_view = sublime.active_window().open_file(path.join(orig_path, orig_story_path))
        views.append(orig_view)      

        return views


class Story:
    """Story class

    Store basic information from a short story
    """

    def __init__(self, content, load_content):
        self._content = content

        if type(self._content) == sublime.View:
            self._parse_from_view()
        else:
            self._parse_from_file(load_content)


    def __str__(self):
        return '"%s" (%d palavras)' % (self.title, self.word_count)


    def _get_header_attribute(self, regex, hdr, number=False):
        """
        Get header attribute from string header

        Returns:
            parsed attribute
        """
        try:
            if not number:
                return re.search(regex, hdr).group(1)
            else:
                return int(re.search(regex, hdr).group(1))
        except Exception as e:
            print('error parsing header: %s\n%s' % (hdr, regex))
            raise e


    def _parse_from_file(self, load_content):
        """
        Parse the story from a string buffer (set in self._content)

        """
        hdr = self._content[:MAX_HEADER]

        self.version = self._get_header_attribute('Versao:\\s+(\\w+)', hdr)
        self.title = self._get_header_attribute('Titulo:\\s+(.*)\\|', hdr).strip(' ')
        self.author = self._get_header_attribute('Autor:\\s+(\\w+)', hdr)
        self.period = self._get_header_attribute('Periodo:\\s+(.*)\\n', hdr)
        self.status = self._get_header_attribute('Status:\\s+(\\w+)', hdr)
        self.word_count = self._get_header_attribute('Palavras:\\s+(\\d+)', hdr, True)

        if load_content:
            init_region = self._content.find(TEXT_REGION_BEGIN) + len(TEXT_REGION_BEGIN) + 1
            end_region = self._content.find(TEXT_REGION_END, init_region)
            self.story_text = self._content[init_region:end_region]
        else:
            self.story_text = ''


    def _parse_from_view(self):
        """
        Parse the story from a view (set in self._content)

        The story text is not reloaded, its Start and End regions are stored
        instead.
        """
        hdr = self._content.substr(sublime.Region(0, MAX_HEADER))

        self.version = self._get_header_attribute('Versao:\\s+(\\w+)', hdr)
        self.title = self._get_header_attribute('Titulo:\\s+(.*)\\|', hdr).strip(' ')
        self.author = self._get_header_attribute('Autor:\\s+(\\w+)', hdr)
        self.period = self._get_header_attribute('Periodo:\\s+(.*)\\n', hdr)
        self.status = self._get_header_attribute('Status:\\s+(\\w+)', hdr)
        self.word_count = self._get_header_attribute('Palavras:\\s+(\\d+)', hdr, True)

        self.init_region = self._content.find(TEXT_REGION_BEGIN, 0, sublime.LITERAL).b
        self.end_region = self._content.find(TEXT_REGION_END, 0, sublime.LITERAL).a


    def get_word_count(self):
        """
        Get word count from the current view

        Returns:
            a tuple containing the Region of the header field and the word count
        """
        region = self._content.find('Palavras:\\s+(\\d+)', 0)
        story_text = self._content.substr(sublime.Region(self.init_region, self.end_region))
        word_count = len(re.findall('\\w+', story_text))

        return region, word_count


    def get_title_region(self):
        """
        Get the title region in the header

        Returns:
            a tuple containing the Region of the header field
        """
        region = self._content.find('Titulo:\\s+(.*)\\|', 0)

        return region

    @staticmethod
    def from_file(file, load_content=False):
        """
        Create a Story object from file

        Returns:
            Story instance
        """
        with open(file) as f:
            content = f.read()

            try:
                story = Story(content, load_content)
                story.path = file

                return story
            except:
                return None


    @staticmethod
    def from_view(view):
        """
        Create a Story object from the current view

        Returns:
            Story instance
        """
        try:
            story = Story(view, False)

            return story
        except Exception as e:
            print(e)
            return None


    @staticmethod
    def format_header_field(field, value):
        """
        Helper function to format a header field and keep the box width
        consistent
        """
        init = '| %s: %s' % (field, value)
        fill = (HEADER_WIDTH - len(init) - 1)*' ' + '|\n'
        return init + fill


    @staticmethod
    def new_header(title='', versao=DRAFT, author=None):
        """
        Create a new header
        """
        hdr = ''
        _author = author

        if _author is None:
            _author = settings.get('author', 'Author')

        _period = date.today().strftime('%d/%m/%Y')

        hdr += '+%s+' % ('-'*(HEADER_WIDTH - 2)) + '\n'
        hdr += Story.format_header_field('Versao', versao)
        hdr += Story.format_header_field('Titulo', title)
        hdr += Story.format_header_field('Autor', _author)
        hdr += Story.format_header_field('Periodo', _period)
        hdr += Story.format_header_field('Status', PENDING)
        hdr += Story.format_header_field('Palavras', 0)
        hdr += Story.format_header_field('Submissoes', '')
        hdr += '+%s+' % ('-'*(HEADER_WIDTH - 2)) + '\n\n'

        return hdr


# --------------------------------------------
# TextCommands
# --------------------------------------------
class ReviseStoryCommand(sublime_plugin.TextCommand):
    """
    Show a list of the stories pending for revision and open a new
    view with the selected one

    Extends:
        sublime_plugin.TextCommand
    """
    def run(self, edit, **args):
        sublime.active_window().open_file(args['pending_revision_list'])


    def input(self, args):
        pending = PendingRevisionList()
        return pending


class TranslateCommand(sublime_plugin.TextCommand):
    """
    Show a list of the stories finished and ready for translation
    and open two views with the selected one

    Extends:
        sublime_plugin.TextCommand
    """
    def run(self, edit, **args):
        window = sublime.active_window()
        window.set_layout({
            'cols': [0.0, 0.5, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            })

        print(window.num_groups())


    def input(self, args):
        return RevisedList()


class NewStoryCommand(sublime_plugin.TextCommand):
    """
    Create a new story (both original and revision versions)

    Extends:
        sublime_plugin.TextCommand
    """
    def run(self, edit):
        m = Manager()
        nf = m.create_original('New Short')
        m.create_revision('New Short')

        sublime.active_window().open_file(nf)


class UpdateWordCount(sublime_plugin.TextCommand):
    """
    Update the word count in the header each time the user
    saves the file

    Extends:
        sublime_plugin.TextCommand
    """
    def run(self, edit, a, b, word_count):
        region = sublime.Region(a, b)
        old_header_line = self.view.full_line(region)

        if self.view.substr(region).find('Palavras') == -1:
            return

        new_count = 'Palavras: %d' % word_count
        new_header = Story.format_header_field('Palavras', word_count)
        self.view.replace(edit, old_header_line, new_header)


class RenameCommand(sublime_plugin.TextCommand):
    """
    Rename the short story. The header and file name
    are edited on both original and revision

    Extends:
        sublime_plugin.TextCommand
    """
    def on_done_title(self, title):
        self.view.run_command('rename', { "title": title, "replace": True })


    def run(self, edit, title, replace = False):
        if not replace:
            new_title = "New Title"
            title_re = re.compile(r'\d+\. (.*)\.txt')

            filename = path.split(self.view.file_name())[1]
            m = title_re.search(filename)

            if m:
                new_title = m.group(1)

            sublime.active_window().show_input_panel('Enter with the new title', new_title, self.on_done_title, None, None)
        else:
            s = Story.from_view(self.view)

            region = s.get_title_region()
            old_header_line = self.view.full_line(region)

            if self.view.substr(region).find('Titulo') == -1:
                return

            new_header = Story.format_header_field('Titulo', title)
            self.view.replace(edit, old_header_line, new_header)


# --------------------------------------------
# ListHandlers
# --------------------------------------------
class PendingRevisionList(sublime_plugin.ListInputHandler):
    def list_items(self):
        str_list = []

        for s in Manager().get_all_pending_for_revision():
            str_list.append((str(s), s.path))

        return str_list


class RevisedList(sublime_plugin.ListInputHandler):
    def list_items(self):
        str_list = []

        for s in Manager().get_all_revised():
            str_list.append((str(s), s.path))

        return str_list


# --------------------------------------------
# EventListeners
# --------------------------------------------
class ViewEventListener(sublime_plugin.ViewEventListener):
    def on_load(self):
        if not self.view.file_name().endswith('.txt'):
            return

        s = Story.from_view(self.view)

        if s is not None:
            self.view.word_count = s.get_word_count()[1]


    def on_modified_async(self):
        if not self.view.file_name().endswith('.txt'):
            #print('%s not a story', name)
            return

        s = Story.from_view(self.view)

        if s is not None and hasattr(self.view, 'word_count'):
            r = s.get_word_count()[1] - self.view.word_count
            self.view.set_status('count_session', 'Sessão: %d palavras' % r)


    def on_pre_save(self):
        if not self.view.file_name().endswith('.txt'):
            return

        s = Story.from_view(self.view)

        if s is not None:
            r = s.get_word_count()
            self.view.run_command('update_word_count', {'a': r[0].a, 'b': r[0].b, 'word_count': r[1]})


    def on_post_save(self):
        if not self.view.file_name().endswith('.txt'):
            return

        m = Manager()
        s = Story.from_view(self.view)

        if s.version == 'Revisao':
            return

        title_re = re.compile(r'(\d+\. ).*\.txt')
        old_filename = path.split(self.view.file_name())[1]
        new_filename = title_re.sub(r'\1%s.txt' % s.title, old_filename)
        
        # saving the current visible region
        visible_region = self.view.visible_region()
        self.view.window().run_command('close_file')

        m.update_file_names(old_filename, new_filename)
        views = m.open_story_files(new_filename)

        # now we return to the saved visible region
        t = threading.Thread(target = show_async, args = (views[0], visible_region))
        t.start()