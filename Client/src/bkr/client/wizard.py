#!/usr/bin/python
#
#   beaker-wizard - tool to ease the creation of a new Beaker test
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
#   Copyright (c) 2009 Red Hat, Inc. All rights reserved.
#
#   This copyrighted material is made available to anyone wishing
#   to use, modify, copy, or redistribute it subject to the terms
#   and conditions of the GNU General Public License version 2.
#
#   This program is distributed in the hope that it will be
#   useful, but WITHOUT ANY WARRANTY; without even the implied
#   warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
#   PURPOSE. See the GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public
#   License along with this program; if not, write to the Free
#   Software Foundation, Inc., 51 Franklin Street, Fifth Floor,
#   Boston, MA 02110-1301, USA.
#
#   Author: Petr Splichal <psplicha@redhat.com>
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

from optparse import OptionParser, OptionGroup, IndentedHelpFormatter
from xml.dom.minidom import parse, parseString
from datetime import date
from time import sleep
import subprocess
import textwrap
import pwd
import sys
import re
import os

# Version
WizardVersion = "2.3.0"

# Regular expressions
RegExpPackage    = re.compile("^(?![._+-])[.a-zA-Z0-9_+-]+(?<![._-])$")
RegExpPath       = re.compile("^(?![/-])[a-zA-Z0-9/_-]+(?<![/-])$")
RegExpTestName   = re.compile("^(?!-)[a-zA-Z0-9-_]+(?<!-)$")
RegExpBug        = re.compile("^\d+$")
RegExpBugLong    = re.compile("^bz\d+$")
RegExpBugPrefix  = re.compile("^bz")
RegExpCVE        = re.compile("^\d{4}-\d{4}$")
RegExpCVELong    = re.compile("^CVE-\d{4}-\d{4}$")
RegExpCVEPrefix  = re.compile("^CVE-")
RegExpAuthor     = re.compile("^[a-zA-Z]+\.?( [a-zA-Z]+\.?){1,2}$")
RegExpEmail      = re.compile("^[a-z._-]+@[a-z.-]+$")
RegExpYes        = re.compile("Everything OK|y|ye|jo|ju|ja|ano|da", re.I)
RegExpReproducer = re.compile("repr|test|expl|poc|demo", re.I)
RegExpScript     = re.compile("\.(sh|py|pl)$")
RegExpMetadata   = re.compile("(\$\(METADATA\):\s+Makefile.*)$", re.S)
RegExpTest       = re.compile("TEST=(\S+)", re.S)
RegExpVersion    = re.compile("TESTVERSION=([\d.]+)", re.S)

# Guesses
GuessAuthorLogin = pwd.getpwuid(os.getuid())[0]
GuessAuthorDomain = re.sub("^.*\.([^.]+\.[^.]+)$", "\\1", os.uname()[1])
GuessAuthorEmail = "%s@%s" % (GuessAuthorLogin, GuessAuthorDomain)
GuessAuthorName = pwd.getpwuid(os.getuid())[4]

# Make sure guesses are valid values
if not RegExpEmail.match(GuessAuthorEmail):
    GuessAuthorEmail = "your@email.com"
if not RegExpAuthor.match(GuessAuthorName):
    GuessAuthorName = "Your Name"

# Commands
GitCommand="git add".split()

# Constants
MaxLengthSuggestedDesc = 50
MaxLenghtTestName = 50
ReviewWidth = 22
MakefileLineWidth = 17
VimDictionary = "# vim: dict=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k"
BugzillaUrl = 'https://bugzilla.redhat.com/show_bug.cgi?id='
BugzillaXmlrpc = 'https://bugzilla.redhat.com/xmlrpc.cgi'
PreferencesDir = os.getenv('HOME') + "/.beaker_client"
PreferencesFile = PreferencesDir + "/wizard"
PreferencesTemplate = """<?xml version="1.0" ?>

<wizard>
    <author>
        <name>%s</name>
        <email>%s</email>
        <confirm>common</confirm>
        <skeleton>beakerlib</skeleton>
    </author>
    <test>
        <time>5m</time>
        <type>Sanity</type>
        <prefix>Yes</prefix>
        <namespace>CoreOS</namespace>
        <priority>Normal</priority>
        <license>GPLv2</license>
        <confidential>No</confidential>
        <destructive>No</destructive>
    </test>
    <licenses>
        <license name="GPLvX">
            This is GPLvX license text.
        </license>
        <license name="GPLvY">
            This is GPLvY license text.
        </license>
        <license name="GPLvZ">
            This is GPLvZ license text.
        </license>
    </licenses>
    <skeletons>
        <skeleton name="skel1">
            This is skeleton 1 example.
        </skeleton>
        <skeleton name="skel2">
            This is skeleton 2 example.
        </skeleton>
        <skeleton name="skel3">
            This is skeleton 3 example.
        </skeleton>
    </skeletons>
</wizard>
""" % (GuessAuthorName, GuessAuthorEmail)


def wrapText(text):
    """ Wrapt text to fit default width """
    text = re.compile("\s+").sub(" ", text)
    return "\n".join(textwrap.wrap(text))

def dedentText(text, count = 12):
    """ Remove leading spaces from the beginning of lines """
    return re.compile("\n" + " " * count).sub("\n", text)

def indentText(text, count = 12):
    """ Insert leading spaces to the beginning of lines """
    return re.compile("\n").sub("\n" + " " * count, text)

def shortenText(text, max = 50):
    """ Shorten long texts into something more usable """
    # if shorter, nothing to do
    if not text or len(text) <= max:
        return text
    # cut the text
    text = text[0:max+1]
    # remove last non complete word
    text = re.sub(" [^ ]*$", "", text)
    return text

def unique(seq):
    """ Remove duplicates from the supplied sequence """
    dictionary = {}
    for i in seq:
        dictionary[i] = 1
    return dictionary.keys()

def hr(width = 70):
    """ Return simple ascii horizontal rule """
    if width < 2: return ""
    return "# " + (width - 2) * "~"

def comment(text, width = 70, comment = "#", top = True, bottom = True, padding = 3):
    """ Create nicely formated comment """
    result = ""
    # top hrule & padding
    if width and top: result += hr(width) + "\n"
    result += int(padding/3) * (comment + "\n")
    # prepend lines with the comment char and padding
    result += re.compile("^(?!#)", re.M).sub(comment + padding * " ", text)
    # bottom padding & hrule
    result += int(padding/3) * ("\n" + comment)
    if width and bottom: result += "\n" + hr(width)
    # remove any trailing spaces
    result = re.compile("\s+$", re.M).sub("", result)
    return result

def dashifyText(text, allowExtraChars = ""):
    """ Replace all special chars with dashes, and perhaps shorten """
    if not text: return text
    # remove the rubbish from the start & end
    text = re.sub("^[^a-zA-Z0-9]*", "", text)
    text = re.sub("[^a-zA-Z0-9]*$", "", text)
    # replace all special chars with dashes
    text = re.sub("[^a-zA-Z0-9%s]+" % allowExtraChars, "-", text)
    return text

def createNode(node, text):
    """ Create a child text node """
    # find document root
    root = node
    while root.nodeType != root.DOCUMENT_NODE:
        root = root.parentNode
    # append child text node
    node.appendChild(root.createTextNode(text))
    return node

def getNode(node):
    """ Return node value """
    try: value = node.firstChild.nodeValue
    except: return None
    else: return value

def setNode(node, value):
    """ Set node value (create a child if necessary) """
    try: node.firstChild.nodeValue = value
    except: createNode(node, value)
    return value

def findNode(parent, tag, name = None):
    """ Find a child node with specified tag (and name) """
    try:
        for child in parent.getElementsByTagName(tag):
            if name is None or child.getAttribute("name") == name:
                return child
    except:
        return None

def findNodeNames(node, tag):
    """ Return list of all name values of specified tags """
    list = []
    for child in node.getElementsByTagName(tag):
        if child.hasAttribute("name"):
            list.append(child.getAttribute("name"))
    return list

def parentDir():
    """ Get parent directory name for package name suggestion """
    dir = re.split("/", os.getcwd())[-1]
    if dir == "": return "kernel"
    # remove the -tests suffix if present
    # (useful if writing tests in the package/package-tests directory)
    dir = re.sub("-tests$", "", dir)
    return dir

def addToGit(path):
    """ Add a file or a directory to Git """

    try:
        process = subprocess.Popen(GitCommand + [path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,)
        out, err = process.communicate()
        if process.wait():
            print "Sorry, failed to add %s to git :-(" % path
            print out, err
            sys.exit(1)
    except OSError:
        print("Unable to run %s, is %s installed?"
                % (" ".join(GitCommand), GitCommand[0]))
        sys.exit(1)


class Preferences:
    """ Test's author preferences """

    def __init__(self):
        """ Set (in future get) user preferences / defaults """
        self.template = parseString(PreferencesTemplate)
        self.firstRun = False
        self.load()

    def parse(self):
        """ Parse values from the xml file """
        # parse list nodes
        for node in "author test licenses skeletons".split():
            exec("self.%s = findNode(self.xml, '%s')" % (node, node))

        # parse single value nodes for author
        for node in "name email confirm skeleton".split():
            exec("self.%s = findNode(self.author, '%s')" % (node, node))
            # if the node cannot be found get the default from template
            if not eval("self." + node):
                print "Could not find <%s> in preferences, using default" % node
                exec("self.%s = findNode(self.template, '%s').cloneNode(True)"
                        % (node, node))
                exec("self.author.appendChild(self.%s)" % node)

        # parse single value nodes for test
        for node in "type namespace time priority confidential destructive " \
                "prefix license".split():
            exec("self.%s = findNode(self.test, '%s')" % (node, node))
            # if the node cannot be found get the default from template
            if not eval("self." + node):
                print "Could not find <%s> in preferences, using default" % node
                exec("self.%s = findNode(self.template, '%s').cloneNode(True)" % (node, node))
                exec("self.test.appendChild(self.%s)" % node)

    def load(self):
        """ Load user preferences (or set to defaults) """
        try:
            self.xml = parse(PreferencesFile)
        except:
            if os.path.exists(PreferencesFile):
                print "I'm sorry, the preferences file seems broken.\n" \
                        "Did you do something ugly to %s?" % PreferencesFile
                sleep(3)
            else:
                self.firstRun = True
            self.xml = self.template
            self.parse()
        else:
            try:
                self.parse()
            except:
                print "Failed to parse %s, falling to defaults." % PreferencesFile
                sleep(3)
                self.xml = self.template
                self.parse()

    def update(self, author, email, confirm, type, namespace, \
            time, priority, confidential, destructive, prefix, license, skeleton):
        """ Update preferences with current settings """
        setNode(self.name, author)
        setNode(self.email, email)
        setNode(self.confirm, confirm)
        setNode(self.type, type)
        setNode(self.namespace, namespace)
        setNode(self.time, time)
        setNode(self.priority, priority)
        setNode(self.confidential, confidential)
        setNode(self.destructive, destructive)
        setNode(self.prefix, prefix)
        setNode(self.license, license)
        setNode(self.skeleton, skeleton)

    def save(self):
        """ Save user preferences """
        # try to create directory
        try:
            os.makedirs(PreferencesDir)
        except OSError, e:
            if e.errno == 17:
                pass
            else:
                print "Cannot create preferences directory %s :-(" % PreferencesDir
                return

        # try to write the file
        try:
            file = open(PreferencesFile, "w")
        except:
            print "Cannot write to %s" % PreferencesFile
        else:
            file.write((self.xml.toxml() + "\n").encode("utf-8"))
            file.close()
            print "Preferences saved to %s" % PreferencesFile
        sleep(1)

    def getAuthor(self): return getNode(self.name)
    def getEmail(self): return getNode(self.email)
    def getConfirm(self): return getNode(self.confirm)
    def getType(self): return getNode(self.type)
    def getPackage(self): return parentDir()
    def getNamespace(self): return getNode(self.namespace)
    def getTime(self): return getNode(self.time)
    def getPriority(self): return getNode(self.priority)
    def getConfidential(self): return getNode(self.confidential)
    def getDestructive(self): return getNode(self.destructive)
    def getPrefix(self): return getNode(self.prefix)
    def getVersion(self): return "1.0"
    def getLicense(self): return getNode(self.license)
    def getSkeleton(self): return getNode(self.skeleton)

    def getLicenseContent(self, license):
        content = findNode(self.licenses, "license", license)
        if content:
            return re.sub("\n\s+$", "", content.firstChild.nodeValue)
        else:
            return None


class Help:
    """ Help texts """

    def __init__(self, options = None):
        if options:
            # display expert usage page only
            if options.expert():
                print self.expert();
                sys.exit(0)
            # show version info
            elif options.ver():
                print self.version();
                sys.exit(0)

    def usage(self):
        return "beaker-wizard [options] [TESTNAME] [BUG/CVE...] or beaker-wizard Makefile"

    def version(self):
        return "beaker-wizard %s" % WizardVersion

    def description(self):
        return dedentText("""Beaker Wizard is a tool which can transform that
            create-all-the-necessary-files-with-correct-names-values-and-paths
            boring phase of every test creation into one line joy. For power
            users there is a lot of inspiration in the extra help page. For
            quick start just cd to your test package directory and simply type:
            "beaker-wizard".""")

    def expert(self):
        return dedentText("""
            NAME:
                beaker-wizard - tool to ease the creation of a new Beaker test

            SYNOPSIS:
                beaker-wizard [options] [TESTNAME] [BUG/CVE ...]

                where TESTNAME is specified as:
                    [[[NAMESPACE/]PACKAGE/]TYPE/][PATH/]NAME

                which can be shortened as you need:
                    TESTNAME
                    TYPE/TESTNAME
                    TYPE/PATH/TESTNAME
                    PACKAGE/TYPE/NAME
                    PACKAGE/TYPE/PATH/NAME
                    NAMESPACE/PACKAGE/TYPE/NAME
                    NAMESPACE/PACKAGE/TYPE/PATH/NAME

                beaker-wizard [path/to/]Makefile

                will run the Wizard in the Makefile edit mode which allows to
                quickly & simply update metadata of an already existing test
                while trying to keep the rest of the Makefile untouched.

            EXAMPLES:
                beaker-wizard overload-performance 379791
                    regression test with specified bug and name
                    -> /CoreOS/perl/Regression/bz379791-overload-performance

                beaker-wizard buffer-overflow 2008-1071 -a i386
                    security test with specified CVE and name, i386 arch only
                    -> /CoreOS/perl/Security/CVE-2008-1071-buffer-overflow

                beaker-wizard Sanity/options -y -a?
                    sanity test with given name, ask just for architecture
                    -> /CoreOS/perl/Sanity/options

                beaker-wizard Sanity/server/smoke
                    add an optional path under test type directory
                    -> /CoreOS/perl/Sanity/server/smoke

                beaker-wizard -by 1234
                    contact bugzilla for details, no questions, just review
                    -> /CoreOS/installer/Regression/bz1234-Swap-partition-Installer

                beaker-wizard -byf 2007-0455
                    security test, no questions, no review, overwrite existing files
                    -> /CoreOS/gd/Security/CVE-2007-0455-gd-buffer-overrun

                All of the previous examples assume you're in the package tests
                directory (e.g. cd git/tests/perl). All the necessary directories and
                files are created under this location.

            TIP:
                If you provide an option with a "?" you will be given a list of
                available options and a prompt to type your choice in.

            PREFERENCES:
                All commonly used preferences can be saved into ~/.beaker_client/wizard.
                Use "write" command to save current settings when reviewing gathered
                test data or edit the file with you favourite editor.

                All options are self-explanatory. For confirm level choose one of:
                nothing, common or everything.

            SKELETONS:
                Another interesting feature is that you can save your own skeletons into
                the preferences file, so that you can automatically populate the new
                test scripts with your favourite structure.

                All of the test related metadata gathered by Wizard can be expanded
                inside the skeletons using xml tags. For example: use <package/> for
                expanding into the test package name or <test/> for the full test name.

                The following metadata variables are available:
                    * test namespace package type path testname description
                    * bugs reproducers requires architectures releases version time
                    * priority license confidential destructive
                    * skeleton author email

            LINKS:
                Beaker Wizard Project Page
                https://fedorahosted.org/beaker/wiki/BeakerWizard

                Beaker Documentation:
                https://fedorahosted.org/beaker/wiki/BeakerUserGuide

                BeakerLib
                https://fedorahosted.org/beakerlib

            BUGS:
                If you find a bug or have an idea for enhancement, do not hesitate
                to contact me on the address below. Or, even better, file a new bug:
                https://fedorahosted.org/beaker/wiki/BeakerWizard#Bugs

            AUTHOR:
                Petr Splichal <psplicha@redhat.com>
                Enjoy the wizard! :-)
            """)


class Makefile:
    """
    Parse values from an existing Makefile to set the initial values
    Used in the Makefile edit mode.
    """

    def __init__(self, options):
        # try to read the original Makefile
        self.path = options.arg[0]
        try:
            # open and read the whole content into self.text
            print "Reading the Makefile..."
            file = open(self.path)
            self.text = "".join(file.readlines())
            file.close()

            # substitute the old style $TEST sub-variables if present
            for var in "TOPLEVEL_NAMESPACE PACKAGE_NAME RELATIVE_PATH".split():
                m = re.search("%s=(\S+)" % var, self.text)
                if m: self.text = re.sub("\$\(%s\)" % var, m.group(1), self.text)

            # locate the metadata section
            print "Inspecting the metadata section..."
            m = RegExpMetadata.search(self.text)
            self.metadata = m.group(1)

            # parse the $TEST and $TESTVERSION
            print "Checking for the full test name and version..."
            m = RegExpTest.search(self.text)
            options.arg = [m.group(1)]
            m = RegExpVersion.search(self.text)
            options.opt.version = m.group(1)
        except:
            print "Failed to parse the original Makefile"
            sys.exit(6)

        # disable test name prefixing and set confirm to nothing
        options.opt.prefix = "No"
        options.opt.confirm = "nothing"

        # initialize non-existent options.opt.* vars
        options.opt.bug = options.opt.owner = options.opt.runfor = None
        # uknown will be used to store unrecognized metadata fields
        self.unknown = ""
        # map long fields to short versions
        map = {
            "description" : "desc",
            "architectures" : "archs",
            "testtime" : "time"
        }

        # parse info from metadata line by line
        print "Parsing the individual metadata..."
        for line in self.metadata.split("\n"):
            m = re.search("echo\s+[\"'](\w+):\s*(.*)[\"']", line)
            # skip non-@echo lines
            if not m: continue
            # read the key & value pair
            try: key = map[m.group(1).lower()]
            except: key = m.group(1).lower()
            # get the value, unescape escaped double quotes
            value = re.sub("\\\\\"", "\"", m.group(2))
            # skip fields known to contain variables
            if key in ("name", "testversion", "path"): continue
            # save known fields into options
            for data in "owner desc type archs releases time priority license " \
                    "confidential destructive bug requires runfor".split():
                if data == key:
                    # if multiple choice, extend the array
                    if key in "archs bug releases requires runfor".split():
                        try: exec("options.opt.%s.append(value)" % key)
                        except: exec("options.opt.%s = [value]" % key)
                    # otherwise just set the value
                    else:
                        exec("options.opt.%s = value" % key)
                    break
            # save unrecognized fields to be able to restore them back
            else:
                self.unknown += "\n" + line

        # parse name & email
        m = re.search("(.*)\s+<(.*)>", options.opt.owner)
        if m:
            options.opt.author = m.group(1)
            options.opt.email = m.group(2)

        # add bug list to arg
        if options.opt.bug:
            options.arg.extend(options.opt.bug)

        # success
        print "Makefile successfully parsed."

    def save(self, test, version, content):
        # possibly update the $TEST and $TESTVERSION
        self.text = RegExpTest.sub("TEST=" + test, self.text)
        self.text = RegExpVersion.sub("TESTVERSION=" + version, self.text)

        # substitute the new metadata
        m = RegExpMetadata.search(content)
        self.text = RegExpMetadata.sub(m.group(1), self.text)

        # add unknown metadata fields we were not able to parse at init
        self.text = re.sub("\n\n\trhts-lint",
                self.unknown + "\n\n\trhts-lint", self.text)

        # let's write it
        try:
            file = open(self.path, "w")
            file.write(self.text.encode("utf-8"))
            file.close()
        except:
            print "Cannot write to %s" % self.path
            sys.exit(3)
        else:
            print "Makefile successfully written"


class Options:
    """
    Class maintaining user preferences and options provided on command line

    self.opt  ... options parsed from command line
    self.pref ... user preferences / defaults
    """

    def __init__(self):
        self.pref = Preferences()
        formatter = IndentedHelpFormatter(max_help_position=40)
        #formatter._long_opt_fmt = "%s"

        # parse options
        parser = OptionParser(Help().usage(), formatter=formatter)
        parser.set_description(Help().description())

        # examples and help
        parser.add_option("-x", "--expert",
            dest="expert",
            action="store_true",
            help="extra help, expert usage, examples")
        parser.add_option("-V", "--version",
            dest="ver",
            action="store_true",
            help="display version info and quit")

        # author
        groupAuthor = OptionGroup(parser, "Author info")
        groupAuthor.add_option("-n",
            dest="author",
            metavar="NAME",
            help="your name [%s]" % self.pref.getAuthor())
        groupAuthor.add_option("-m",
            dest="email",
            metavar="MAIL",
            help="your email address [%s]" %  self.pref.getEmail())

        # create
        groupCreate = OptionGroup(parser, "Test creation specifics")
        groupCreate.add_option("-s",
            dest="skeleton",
            help="skeleton to use [%s]" % self.pref.getSkeleton())
        groupCreate.add_option("-j",
            dest="prefix",
            metavar="PREFIX",
            help="join the bug prefix to the testname [%s]"
                    % self.pref.getPrefix())
        groupCreate.add_option("-f", "--force",
            dest="force",
            action="store_true",
            help="force without review and overwrite existing files")
        groupCreate.add_option("-w", "--write",
            dest="write",
            action="store_true",
            help="write preferences to ~/.beaker_client/wizard")
        groupCreate.add_option("-b", "--bugzilla",
            dest="bugzilla",
            action="store_true",
            help="contact bugzilla to get bug details")
        groupCreate.add_option("-g", "--git",
            dest="git",
            action="store_true",
            help="add created files to the git repository")

        # setup default to correctly display in help
        defaultEverything = defaultCommon = defaultNothing = ""
        if self.pref.getConfirm() == "everything":
            defaultEverything = " [Default]"
        elif self.pref.getConfirm() == "common":
            defaultCommon = " [Default]"
        elif self.pref.getConfirm() == "nothing":
            defaultNothing = " [Default]"

        # confirm
        groupConfirm = OptionGroup(parser, "Confirmation and verbosity")
        groupConfirm.add_option("-v", "--verbose",
            dest="verbose",
            action="store_true",
            help="display detailed info about every action")
        groupConfirm.add_option("-e", "--every",
            dest="confirm",
            action="store_const",
            const="everything",
            help="prompt for each and every available option" + defaultEverything)
        groupConfirm.add_option("-c", "--common",
            dest="confirm",
            action="store_const",
            const="common",
            help="confirm only commonly used options" + defaultCommon)
        groupConfirm.add_option("-y", "--yes",
            dest="confirm",
            action="store_const",
            const="nothing",
            help="yes, I'm sure, no questions, just do it!" + defaultNothing)

        # test metadata
        groupMeta = OptionGroup(parser, "Basic metadata")
        groupMeta.add_option("-d",
            dest="desc",
            metavar="DESCRIPTION",
            help="short description")
        groupMeta.add_option("-a",
            dest="archs",
            action="append",
            help="architectures [All]")
        groupMeta.add_option("-r",
            dest="releases",
            action="append",
            help="releases [All]")
        groupMeta.add_option("-o",
            dest="runfor",
            action="append",
            metavar="PACKAGES",
            help="run for packages [%s]" % self.pref.getPackage())
        groupMeta.add_option("-q",
            dest="requires",
            action="append",
            metavar="PACKAGES",
            help="required packages [%s]" % self.pref.getPackage())
        groupMeta.add_option("-t",
            dest="time",
            help="test time [%s]" % self.pref.getTime())

        # test metadata
        groupExtra = OptionGroup(parser, "Extra metadata")
        groupExtra.add_option("-z",
            dest="version",
            help="test version [%s]" % self.pref.getVersion())
        groupExtra.add_option("-p",
            dest="priority",
            help="priority [%s]" % self.pref.getPriority())
        groupExtra.add_option("-l",
            dest="license",
            help="license [%s]" % self.pref.getLicense())
        groupExtra.add_option("-i",
            dest="confidential",
            metavar="INTERNAL",
            help="confidential [%s]" % self.pref.getConfidential())
        groupExtra.add_option("-u",
            dest="destructive",
            metavar="UGLY",
            help="destructive [%s]" % self.pref.getDestructive())

        # put it together
        parser.add_option_group(groupMeta)
        parser.add_option_group(groupExtra)
        parser.add_option_group(groupAuthor)
        parser.add_option_group(groupCreate)
        parser.add_option_group(groupConfirm)

        # convert all args to unicode
        uniarg = []
        for arg in sys.argv[1:]:
             uniarg.append(unicode(arg, "utf-8"))

        # and parse it!
        (self.opt, self.arg) = parser.parse_args(uniarg)

        # parse namespace/package/type/path/test
        self.opt.namespace = None
        self.opt.package = None
        self.opt.type = None
        self.opt.path = None
        self.opt.name = None
        self.opt.bugs = []
        self.makefile = False

        if self.arg:
            # if we're run in the Makefile-edit mode, parse it to get the values
            if re.match(".*Makefile$", self.arg[0]):
                self.makefile = Makefile(self)

            # the first arg looks like bug/CVE -> we take all args as bugs/CVE's
            if RegExpBug.match(self.arg[0]) or RegExpBugLong.match(self.arg[0]) or \
                    RegExpCVE.match(self.arg[0]) or RegExpCVELong.match(self.arg[0]):
                self.opt.bugs = self.arg[:]
            # otherwise we expect bug/CVE as second and following
            else:
                self.opt.bugs = self.arg[1:]
                # parsing namespace/package/type/path/testname
                self.testinfo = self.arg[0]
                regex = re.compile("^(?:(?:(?:/?%s/)?([^/]+)/)?%s/)?(?:([^/]+)/)?([^/]+)$" %
                    (Namespace().match(), Type().match()))
                matched = regex.match(self.testinfo)
                if matched:
                    (self.opt.namespace, self.opt.package, self.opt.type, \
                            self.opt.path, self.opt.name) = matched.groups()

        # try to connect to bugzilla
        self.bugzilla = None
        if self.opt.bugzilla:
            try:
                from bugzilla import Bugzilla
            except:
                print "Sorry, the bugzilla interface is not available right now, try:\n" \
                        "    yum install python-bugzilla\n" \
                        "Use 'bugzilla login' command if you wish to access restricted bugs."
                sys.exit(8)
            else:
                try:
                    print "Contacting bugzilla..."
                    self.bugzilla = Bugzilla(url=BugzillaXmlrpc)
                except:
                    print "Cannot connect to bugzilla, check your net connection."
                    sys.exit(9)

    # command-line-only option interface
    def expert(self):   return self.opt.expert
    def ver(self):      return self.opt.ver
    def force(self):    return self.opt.force
    def write(self):    return self.opt.write
    def verbose(self):  return self.pref.firstRun or self.opt.verbose
    def confirm(self):  return self.opt.confirm or self.pref.getConfirm()

    # return both specified and default values for the rest of options
    def author(self):       return [ self.opt.author,       self.pref.getAuthor() ]
    def email(self):        return [ self.opt.email,        self.pref.getEmail() ]
    def skeleton(self):     return [ self.opt.skeleton,     self.pref.getSkeleton() ]
    def archs(self):        return [ self.opt.archs,        [] ]
    def releases(self):     return [ self.opt.releases,     [] ]
    def runfor(self):       return [ self.opt.runfor,       [self.pref.getPackage()] ]
    def requires(self):     return [ self.opt.requires,     [self.pref.getPackage()] ]
    def time(self):         return [ self.opt.time,         self.pref.getTime() ]
    def priority(self):     return [ self.opt.priority,     self.pref.getPriority() ]
    def confidential(self): return [ self.opt.confidential, self.pref.getConfidential() ]
    def destructive(self):  return [ self.opt.destructive,  self.pref.getDestructive() ]
    def prefix(self):       return [ self.opt.prefix,       self.pref.getPrefix() ]
    def license(self):      return [ self.opt.license,      self.pref.getLicense() ]
    def version(self):      return [ self.opt.version,      self.pref.getVersion() ]
    def desc(self):         return [ self.opt.desc,         "What the test does" ]
    def description(self):  return [ self.opt.description,  "" ]
    def namespace(self):    return [ self.opt.namespace,    self.pref.getNamespace() ]
    def package(self):      return [ self.opt.package,      self.pref.getPackage() ]
    def type(self):         return [ self.opt.type,         self.pref.getType() ]
    def path(self):         return [ self.opt.path,         "" ]
    def name(self):         return [ self.opt.name,         "a-few-descriptive-words" ]
    def bugs(self):         return [ self.opt.bugs,         [] ]



class Inquisitor:
    """
    Father of all Inquisitors

    Well he is not quite real Inquisitor, as he is very
    friendly and accepts any answer you give him.
    """
    def __init__(self, options = None, suggest = None):
        # set options & initialize
        self.options = options
        self.suggest = suggest
        self.common = True
        self.error = 0
        self.init()
        if not self.options: return

        # finally ask for confirmation or valid value
        if self.confirm or not self.valid():
            self.ask()

    def init(self):
        """ Initialize basic stuff """
        self.name = "Answer"
        self.question = "What is the answer to life, the universe and everything"
        self.description = None
        self.default()

    def default(self, optpref):
        """ Initialize default option data """
        # nothing to do when options not supplied
        if not optpref: return

        # initialize opt (from command line) & pref (from user preferences)
        (self.opt, self.pref) = optpref

        # set confirm flag
        self.confirm = self.common and self.options.confirm() != "nothing" \
                or not self.common and self.options.confirm() == "everything"

        # now set the data!
        # commandline option overrides both preferences & suggestion
        if self.opt:
            self.data = self.opt
            self.confirm = False
        # use suggestion if available (disabled in makefile edit mode)
        elif self.suggest and not self.options.makefile:
            self.data = self.suggest
        # otherwise use the default from user preferences
        else:
            self.data = self.pref
            # reset the user preference if it's not a valid value
            # (to prevent suggestions like: x is not valid what about x?)
            if not self.valid():
                self.pref = "something else"

    def defaultify(self):
        """ Set data to default/preferred value """
        self.data = self.pref

    def normalize(self):
        """ Remove trailing and double spaces """
        if not self.data: return
        self.data = re.sub("^\s*", "", self.data)
        self.data = re.sub("\s*$", "", self.data)
        self.data = re.sub("\s+", " ", self.data)

    def read(self):
        """ Read an answer from user """
        try:
            answer = unicode(sys.stdin.readline().strip(), "utf-8")
        except KeyboardInterrupt:
            print "\nOk, finishing for now. See you later ;-)"
            sys.exit(4)
        # if just enter pressed, we leave self.data as it is (confirmed)
        if answer != "":
            # append the data if the answer starts with a "+"
            m = re.search("^\+\s*(.*)", answer)
            if m and type(self.data) is list:
                self.data.append(m.group(1))
            else:
                self.data = answer
        self.normalize()

    def heading(self):
        """ Display nice heading with question """
        print "\n" + self.question + "\n" + 77 * "~";

    def value(self):
        """ Return current value """
        return self.data

    def show(self, data = None):
        """ Return current value nicely formatted (redefined in children)"""
        if not data: data = self.data
        if data == "": return "None"
        return data

    def singleName(self):
        """ Return the name in lowercase singular (for error reporting) """
        return re.sub("s$", "", self.name.lower())

    def matchName(self, text):
        """ Return true if the text matches inquisitor's name """
        # remove any special characters from the search string
        text = re.sub("[^\w\s]", "", text)
        return re.search(text, self.name, re.I)

    def describe(self):
        if self.description is not None:
            print wrapText(self.description)

    def format(self, data = None):
        """ Display in a nicely indented style """
        print self.name.rjust(ReviewWidth), ":", (data or self.show())

    def formatMakefileLine(self, name = None, value = None):
        """ Format testinfo line for Makefile inclusion """
        if not (self.value() or value): return ""
        return '\n            	@echo "%s%s" >> $(METADATA)' % (
                ((name or self.name) + ":").ljust(MakefileLineWidth),
                re.sub("\"", "\\\"", value or self.value()))

    def valid(self):
        """ Return true when provided value is a valid answer """
        return self.data not in ["?", ""]

    def suggestion(self):
        """ Provide user with a suggestion or detailed description """
        # if current data is valid, offer is as a suggestion
        if self.valid():
            if self.options.verbose(): self.describe()
            return "%s?" % self.show()
        # otherwise suggest the default value
        else:
            bad = self.data
            self.defaultify()

            # regular suggestion (no question mark for help)
            if bad is None or "".join(bad) != "?":
                self.error += 1
                if self.error > 1 or self.options.verbose(): self.describe()
                return "%s is not a valid %s, what about %s?" \
                    % (self.show(bad), self.singleName(), self.show(self.pref))
            # we got question mark ---> display description to help
            else:
                self.describe()
                return "%s?" % self.show()

    def ask(self, force = False, suggest = None):
        """ Ask for valid value """
        if force: self.confirm = True
        if suggest: self.data = suggest
        self.heading()
        # keep asking until we get sane answer
        while self.confirm or not self.valid():
            sys.stdout.write("[%s] " % self.suggestion().encode("utf-8"))
            self.read()
            self.confirm = False

    def edit(self, suggest = None):
        """ Edit = force to ask again
        returns true if changes were made """
        before = self.data
        self.ask(force = True, suggest = suggest)
        return self.data != before


class SingleChoice(Inquisitor):
    """ This Inquisitor accepts just one value from the given list """

    def init(self):
        self.name = "SingleChoice"
        self.question = "Give a valid answer from the list"
        self.description = "Supply a single value from the list above."
        self.list = ["list", "of", "valid", "values"]
        self.default()

    def propose(self):
        """ Try to find nearest match in the list"""
        if self.data == "?": return
        for item in self.list:
            if re.search(self.data, item, re.I):
                self.pref = item
                return

    def valid(self):
        if self.data in self.list:
            return True
        else:
            self.propose()
            return False

    def heading(self):
        Inquisitor.heading(self)
        if self.list: print wrapText("Possible values: " + ", ".join(self.list))


class YesNo(SingleChoice):
    """ Inquisitor expecting only two obvious answers """

    def init(self):
        self.name = "Yes or No"
        self.question = "Are you sure?"
        self.description = "All you need to say is simply 'Yes,' or 'No'; \
                anything beyond this comes from the evil one."
        self.list = ["Yes", "No"]
        self.default()

    def normalize(self):
        """ Recognize yes/no abbreviations """
        if not self.data: return
        self.data = re.sub("^y.*$", "Yes", self.data, re.I)
        self.data = re.sub("^n.*$", "No", self.data, re.I)

    def formatMakefileLine(self, name = None, value = None):
        """ Format testinfo line for Makefile inclusion """
        # testinfo requires lowercase yes/no
        return Inquisitor.formatMakefileLine(self,
                name = name, value = self.data.lower())

    def valid(self):
        self.normalize()
        return SingleChoice.valid(self)


class MultipleChoice(SingleChoice):
    """ This Inquisitor accepts more values but only from the given list """

    def init(self):
        self.name = "MultipleChoice"
        self.question = "Give one or more values from the list"
        self.description = "You can supply more values separated with space or comma\n"\
            "but they all must be from the list above."
        self.list = ["list", "of", "valid", "values"]
        self.emptyListMeaning = "None"
        self.sort = True
        self.default()

    def default(self, optpref):
        # initialize opt & pref
        (self.opt, self.pref) = optpref

        # set confirm flag
        self.confirm = self.common and self.options.confirm() != "nothing" \
                or not self.common and self.options.confirm() == "everything"

        # first initialize data as an empty list
        self.data = []

        # append possible suggestion to the data (disabled in makefile edit mode)
        if self.suggest and not self.options.makefile:
            self.data.append(self.suggest)

        # add items obtained from the command line
        if self.opt:
            self.data.extend(self.opt)
            self.confirm = False

        # default preferences used only if still no data obtained
        if not self.data:
            self.data.extend(self.pref)

        self.listify()

    def defaultify(self):
        self.data = self.pref[:]
        self.listify()

    def listify(self):
        # make sure data is list
        if type(self.data) is not list:
            # special value "none" means an empty list
            if self.data.lower() == "none":
                self.data = []
                return
            # depending on emptyListMeaning "all" can mean
            elif self.data.lower() == "all":
                # no restrictions (releases, archs)
                if self.emptyListMeaning == "All":
                    self.data = []
                # all items (reproducers)
                else:
                    self.data = self.list[:]
                return
            # otherwise just listify
            else:
                self.data = [ self.data ]

        # expand comma/space separated items
        result = []
        for item in self.data:
            # strip trailing separators
            item = re.sub('[ ,]*$', '', item)
            # split on spaces and commas
            result.extend(re.split('[ ,]+', item))
        self.data = result

        # let's make data unique and sorted
        if self.sort:
            self.data = unique(self.data)
            self.data.sort()

    def normalize(self):
        """ Parse input into a list """
        self.listify()

    def showItem(self, item):
        return item

    def formatMakefileLine(self, name = None, value = None):
        """ Format testinfo line for Makefile inclusion """
        # for multiple choice we produce values joined by spaces
        return Inquisitor.formatMakefileLine(self,
                name = name, value = " ".join(self.data))

    def show(self, data = None):
        if data is None: data = self.data
        if not data: return self.emptyListMeaning
        return ", ".join(map(self.showItem, data))

    def propose(self):
        """ Try to find nearest matches in the list"""
        if self.data[0] == "?": return
        result = []
        try:
            for item in self.list:
                if re.search(self.data[0], item, re.I):
                    result.append(item)
        except:
            pass
        if result:
            self.pref = result[:]

    def validItem(self, item):
        return item in self.list

    def valid(self):
        for item in self.data:
            if not self.validItem(item):
                self.data = [item]
                self.propose()
                return False
        return True


class License(Inquisitor):
    """ License to be included in test files """

    def init(self):
        self.name = "License"
        self.question = "What licence should be used?"
        self.description = "Just supply a license GPLv2, GPLv3, ..."
        self.common = False
        self.default(self.options.license())
        self.licenses = {
            "GPLv2" : """Copyright (c) %s Red Hat, Inc. All rights reserved.
            
            This copyrighted material is made available to anyone wishing
            to use, modify, copy, or redistribute it subject to the terms
            and conditions of the GNU General Public License version 2.
            
            This program is distributed in the hope that it will be
            useful, but WITHOUT ANY WARRANTY; without even the implied
            warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
            PURPOSE. See the GNU General Public License for more details.
            
            You should have received a copy of the GNU General Public
            License along with this program; if not, write to the Free
            Software Foundation, Inc., 51 Franklin Street, Fifth Floor,
            Boston, MA 02110-1301, USA.""" % date.today().year,


            "GPLv3" : """Copyright (c) %s Red Hat, Inc. All rights reserved.
            
            This program is free software: you can redistribute it and/or
            modify it under the terms of the GNU General Public License as
            published by the Free Software Foundation, either version 3 of
            the License, or (at your option) any later version.
            
            This program is distributed in the hope that it will be
            useful, but WITHOUT ANY WARRANTY; without even the implied
            warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
            PURPOSE.  See the GNU General Public License for more details.
            
            You should have received a copy of the GNU General Public License
            along with this program. If not, see http://www.gnu.org/licenses/."""
            % date.today().year,

            "other" : """Copyright (c) %s Red Hat, Inc. All rights reserved.

            %s"""}

    def get(self):
        """ Return license corresponding to user choice """
        if self.data != "other" and self.data in self.licenses.keys():
            return dedentText(self.licenses[self.data])
        else:
            license = self.options.pref.getLicenseContent(self.data)
            if license: # user defined license from preferences
                return dedentText(self.licenses["other"] % (
                        date.today().year, license), count = 12)
            else: # anything else
                return dedentText(self.licenses["other"] % (
                        date.today().year, "PROVIDE YOUR LICENSE TEXT HERE."))


class Time(Inquisitor):
    """ Time for test to run """

    def init(self):
        self.name = "Time"
        self.question = "Time for test to run"
        self.description = """The time must be in format [1-99][m|h|d] for 1-99
                minutes/hours/days (e.g. 3m, 2h, 1d)"""
        self.default(self.options.time())

    def valid(self):
        m = re.match("^(\d{1,2})[mhd]$", self.data)
        return m is not None and int(m.group(1)) > 0


class Version(Inquisitor):
    """ Time for test to run """

    def init(self):
        self.name = "Version"
        self.question = "Version of the test"
        self.description = "Must be in the format x.y"
        self.common = False
        self.default(self.options.version())

    def valid(self):
        return re.match("^\d+\.\d+$", self.data)


class Priority(SingleChoice):
    """ Test priority """

    def init(self):
        self.name = "Priority"
        self.question = "Priority"
        self.description = "Test priority for scheduling purposes"
        self.common = False
        self.list = "Low Medium Normal High Manual".split()
        self.default(self.options.priority())


class Confidential(YesNo):
    """ Confidentiality flag """

    def init(self):
        self.name = "Confidential"
        self.question = "Confidential"
        self.description = "Should the test be kept internal?"
        self.common = False
        self.list = ["Yes", "No"]
        self.default(self.options.confidential())

    def singleName(self):
        return "confidentiality flag"


class Destructive(YesNo):
    """ Destructivity flag """

    def init(self):
        self.name = "Destructive"
        self.question = "Destructive"
        self.description = "Is it such an ugly test that it can break the system?"
        self.common = False
        self.list = ["Yes", "No"]
        self.default(self.options.destructive())

    def singleName(self):
        return "destructivity flag"


class Prefix(YesNo):
    """ Bug number prefix """

    def init(self):
        self.name = "Prefix the test name"
        self.question = "Add the bug number to the test name?"
        self.description = "Should we prefix the test name with the bug/CVE number?"
        self.common = False
        self.list = ["Yes", "No"]
        self.default(self.options.prefix())

    def singleName(self):
        return "prefix choice"


class Releases(MultipleChoice):
    """ List of releases the test should run on """

    def init(self):
        self.name = "Releases"
        self.question = "Releases (choose one or more or \"all\")"
        self.description = """One or more values separated with space or comma
            or "all" for no limitaion. You can also use minus sign for excluding
            a specific release (-RHEL4)"""
        self.list = "RHEL2.1 RHEL3 RHEL4 RHELServer5 RHELClient5".split()
        self.list += ["RHEL{0}".format(id) for id in range(6, 9)]
        self.list += "FC4 FC5 FC6".split()
        self.list += ["F{0}".format(release) for release in range(7, 28)]
        self.sort = True
        self.common = False
        self.emptyListMeaning = "All"
        self.default(self.options.releases())

    def validItem(self, item):
        item = re.sub("^-","", item)
        return item in self.list


class Architectures(MultipleChoice):
    """ List of architectures the test should run on """

    def init(self):
        self.name = "Architectures"
        self.question = "Architectures (choose one or more or \"all\")"
        self.description = "You can supply more values separated with space or comma\n"\
            "but they all must be from the list of possible values above."
        self.list = "i386 x86_64 ia64 ppc ppc64 s390 s390x".split()
        self.sort = True
        self.common = False
        self.emptyListMeaning = "All"
        self.default(self.options.archs())


class Namespace(SingleChoice):
    """ Namespace"""

    def init(self):
        self.name = "Namespace"
        self.question = "Namespace"
        self.description = "Provide a root namespace for the test."
        self.list = """distribution installation kernel desktop tools CoreOS
                cluster rhn examples performance ISV virt""".split()
        if self.options: self.default(self.options.namespace())

    def match(self):
        """ Return regular expression matching valid data """
        return "(" + "|".join(self.list) + ")"


class Package(Inquisitor):
    """ Package for which the test is written """

    def init(self):
        self.name = "Package"
        self.question = "What package is this test for?"
        self.description = "Supply a package name (without version or release number)"
        self.common = False
        self.default(self.options.package())

    def valid(self):
        return RegExpPackage.match(self.data)


class Type(SingleChoice):
    """ Test type """

    def init(self):
        self.name = "Test type"
        self.question = "What is the type of test?"
        self.description = "Test type must be exactly one from the list above."
        self.list = """Regression Performance Stress Certification
            Security Durations Interoperability Standardscompliance
            Customeracceptance Releasecriterium Crasher Tier1 Tier2
            Alpha KernelTier1 KernelTier2 Multihost MultihostDriver
            Install FedoraTier1 FedoraTier2 KernelRTTier1
            KernelReporting Sanity""".split()
        if self.options: self.default(self.options.type())

    def match(self):
        """ Return regular expression matching valid data """
        return "(" + "|".join(self.list) + ")"

    def suggestSkeleton(self):
        """ For multihost tests suggest proper skeleton """
        if self.data == "Multihost":
            return "multihost"
        else:
            return None


class Path(Inquisitor):
    """ Relative path to test """

    def init(self):
        self.name = "Relative path"
        self.question = "Relative path under test type"
        self.description = """Path can be used to organize tests
            for complex packages, e.g. 'server' part in
            /CoreOS/mysql/Regression/server/bz123456-some-test.
            (You can also use dir/subdir for deeper nesting.
            Use "none" for no path.)"""
        self.common = False
        self.default(self.options.path())

    def valid(self):
        return (self.data is None or self.data == ""
                or RegExpPath.match(self.data))

    def normalize(self):
        """ Replace none keyword with real empty path """
        Inquisitor.normalize(self)
        if self.data and re.match('none', self.data, re.I):
            self.data = None

    def value(self):
        if self.data:
            return "/" + self.data
        else:
            return ""


class Bugs(MultipleChoice):
    """ List of bugs/CVE's related to the test """

    def init(self):
        self.name = "Bug or CVE numbers"
        self.question = "Bugs or CVE's related to the test"
        self.description = """Supply one or more bug or CVE numbers
                (e.g. 123456 or 2009-7890). Use the '+' sign to add
                the bugs instead of replacing the current list."""
        self.list = []
        self.sort = False
        self.emptyListMeaning = "None"
        self.bug = None
        self.default(self.options.bugs())
        self.reproducers = Reproducers(self.options)

    def validItem(self, item):
        return RegExpBug.match(item) \
            or RegExpCVE.match(item)

    def valid(self):
        # let's remove possible (otherwise harmless) bug/CVE prefixes
        for i in range(len(self.data)):
            self.data[i] = re.sub(RegExpBugPrefix, "", self.data[i])
            self.data[i] = re.sub(RegExpCVEPrefix, "", self.data[i])
        # and do the real validation
        return MultipleChoice.valid(self)

    def showItem(self, item):
        if RegExpBug.match(item):
            return "BZ#" + item
        elif RegExpCVE.match(item):
            return "CVE-" + item
        else:
            return item

    def formatMakefileLine(self, name = None, value = None):
        """ Format testinfo line for Makefile inclusion """
        list = []
        # filter bugs only (CVE's are not valid for testinfo.desc)
        for item in self.data:
            if RegExpBug.match(item):
                list.append(item)
        if not list: return ""
        return Inquisitor.formatMakefileLine(self, name = "Bug", value = " ".join(list))

    def getFirstBug(self):
        """ Return first bug/CVE if there is some """
        if self.data: return self.showItem(self.data[0])

    def fetchBugDetails(self):
        """ Fetch details of the first bug from Bugzilla """
        if self.options.bugzilla and self.data:
            # use CVE prefix when searching for CVE's in bugzilla
            if RegExpCVE.match(self.data[0]):
                bugid = "CVE-" + self.data[0]
            else:
                bugid = self.data[0]
            # contact bugzilla and try to fetch the details
            try:
                print "Fetching details for", self.showItem(self.data[0])
                self.bug = self.options.bugzilla.getbug(bugid)
            except Exception, e:
                if re.search('not authorized to access', str(e)):
                    print "Sorry, %s has a restricted access.\n"\
                        "Use 'bugzilla login' command to set up cookies "\
                        "then try again." % self.showItem(self.data[0])
                else:
                    print "Sorry, could not get details for %s\n%s" % (bugid, e)
                sleep(3)
                return
            # successfully fetched
            else:
                # for CVE's add the bug id to the list of bugs
                if RegExpCVE.match(self.data[0]):
                    self.data.append(str(self.bug.id))
                # else investigate for possible CVE alias
                elif self.bug.alias and RegExpCVELong.match(self.bug.alias[0]):
                    cve = re.sub("CVE-", "", self.bug.alias[0])
                    self.data[:0] = [cve]
                # and search attachments for possible reproducers
                if self.bug:
                    self.reproducers.find(self.bug)
                    return True

    def getSummary(self):
        """ Return short summary fetched from bugzilla """
        if self.bug:
            return re.sub("CVE-\d{4}-\d{4}\s*", "", self.bug.summary)

    def getComponent(self):
        """ Return bug component fetched from bugzilla """
        # ... and ignore generic CVE component "vulnerability"
        if self.bug and self.bug.component[0] != 'vulnerability':
            return self.bug.component[0]

    def getLink(self):
        """ Return URL of the first bug """
        if self.data:
            if RegExpCVE.match(self.data[0]):
                return "%sCVE-%s" % (BugzillaUrl, self.data[0])
            else:
                return BugzillaUrl + self.data[0]

    def suggestType(self):
        """ Guess test type according to first bug/CVE """
        if self.data:
            if RegExpBug.match(self.data[0]):
                return "Regression"
            elif RegExpCVE.match(self.data[0]):
                return "Security"

    def suggestConfidential(self):
        """ If the first bug is a CVE, suggest as confidential """
        if self.data and RegExpCVE.match(self.data[0]):
            return "Yes"
        else:
            return None

    def suggestTestName(self):
        """ Suggest testname from bugzilla summary """
        return dashifyText(shortenText(self.getSummary(), MaxLenghtTestName))

    def suggestDescription(self):
        """ Suggest short description from bugzilla summary """
        if self.getSummary():
            return "Test for %s (%s)" % (
                self.getFirstBug(),
                shortenText(re.sub(":", "", self.getSummary()),
                        max=MaxLengthSuggestedDesc))

    def formatBugDetails(self):
        """ Put details fetched from Bugzilla into nice format for PURPOSE file """
        if not self.bug:
            return ""
        else:
            return "Bug summary: %s\nBugzilla link: %s\n" % (
                    self.getSummary(), self.getLink())


class Name(Inquisitor):
    """ Test name """

    def init(self):
        self.name = "Test name"
        self.question = "Test name"
        self.description = """Use few, well chosen words describing
            what the test does. Special chars will be automatically
            converted to dashes."""
        self.default(self.options.name())
        self.data = dashifyText(self.data, allowExtraChars="_")
        self.bugs = Bugs(self.options)
        self.bugs.fetchBugDetails()
        # suggest test name (except when supplied on command line)
        if self.bugs.suggestTestName() and not self.opt:
            self.data = self.bugs.suggestTestName()
        self.prefix = Prefix(self.options)

    def normalize(self):
        """ Add auto-dashify function for name editing """
        if not self.data == "?":
            # when editing the test name --- dashify, but allow
            # using underscore if the user really wants it
            self.data = dashifyText(self.data, allowExtraChars="_")

    def valid(self):
        return self.data is not None and RegExpTestName.match(self.data)

    def value(self):
        """ Return test name (including bug/CVE number) """
        bug = self.bugs.getFirstBug()
        if bug and self.prefix.value() == "Yes":
            return bug.replace('BZ#','bz') + "-" + self.data
        else:
            return self.data

    def format(self, data = None):
        """ When formatting let's display with bug/CVE numbers """
        Inquisitor.format(self, self.value())

class Reproducers(MultipleChoice):
    """ Possible reproducers from Bugzilla """

    def init(self):
        self.name = "Reproducers to fetch"
        self.question = "Which Bugzilla attachments do you wish to download?"
        self.description = """Wizard can download Bugzilla attachments for you.
                It suggests those which look like reproducers, but you can pick
                the right attachments manually as well."""
        self.bug = None
        self.list = []
        self.sort = True
        self.emptyListMeaning = "None"
        self.common = False
        self.default([[], []])
        self.confirm = False

    def singleName(self):
        return "reproducer"

    def find(self, bug):
        """ Get the list of all attachments (except patches and obsolotes)"""

        if not bug or not bug.attachments:
            return False
        # remember the bug & empty the lists
        self.bug = bug
        self.list = []
        self.pref = []
        self.data = []

        print "Examining attachments for possible reproducers"
        for attachment in self.bug.attachments:
            # skip obsolete and patch attachments
            if attachment['ispatch'] == 0 and attachment['isobsolete'] == 0:
                self.list.append(attachment['filename'])
                # add to suggested attachments if it looks like a reproducer
                if RegExpReproducer.search(attachment['description']) or \
                        RegExpReproducer.search(attachment['filename']):
                    self.data.append(attachment['filename'])
                    self.pref.append(attachment['filename'])
                    print "Adding",
                else:
                    print "Skipping",
                print "%s (%s)" % (attachment['filename'], attachment['description'])
                sleep(1)

    def download(self, path):
        """ Download selected reproducers """
        if not self.bug:
            return False
        for attachment in self.bug.attachments:
            if attachment['filename'] in self.data \
                    and attachment['isobsolete'] == 0:
                print "Attachment", attachment['filename'],
                try:
                    dirfiles = os.listdir(path)
                    filename = path + "/" + attachment['filename']
                    remote = self.options.bugzilla.openattachment(
                            attachment['id'])
                    # rename the attachment if it has the same name as one
                    # of the files in the current directory
                    if attachment['filename'] in dirfiles:
                        print "- file already exists in {0}/".format(path)
                        new_name = ""
                        while new_name == "":
                            print "Choose a new filename for the attachment: ",
                            new_name = unicode(
                                    sys.stdin.readline().strip(), "utf-8")
                        filename = path + "/" + new_name

                    local = open(filename, 'w')
                    local.write(remote.read())
                    remote.close()
                    local.close()

                    # optionally add to the git repository
                    if self.options.opt.git:
                        addToGit(filename)
                        addedToGit = ", added to git"
                    else:
                        addedToGit = ""
                except:
                    print "download failed"
                    print "python-bugzilla-0.5 or higher required"
                    sys.exit(5)
                else:
                    print "downloaded" + addedToGit


class RunFor(MultipleChoice):
    """ List of packages which this test should be run for """

    def init(self):
        self.name = "Run for packages"
        self.question = "Run for packages"
        self.description = """Provide a list of packages which this test should
                be run for. It's a good idea to add dependent packages here."""
        self.list = []
        self.sort = True
        self.emptyListMeaning = "None"
        self.common = False
        self.default(self.options.runfor())

    def validItem(self, item):
        return RegExpPackage.match(item)


class Requires(MultipleChoice):
    """ List of packages which should be installed on test system """

    def init(self):
        self.name = "Required packages"
        self.question = "Requires: packages which test depends on"
        self.description = """Just write a list of package names
                which should be automatically installed on the test system."""
        self.list = []
        self.sort = True
        self.emptyListMeaning = "None"
        self.common = False
        self.default(self.options.requires())

    def validItem(self, item):
        return RegExpPackage.match(item)


class Skeleton(SingleChoice):
    """ Skeleton to be used for creating the runtest.sh """

    def init(self):
        self.name = "Skeleton"
        self.question = "Skeleton to be used for creating the runtest.sh"
        self.description = """There are several runtest.sh skeletons available:
                beaker (general Beaker template),
                beakerlib (BeakerLib structure),
                simple (creates separate script with test logic),
                empty (populates runtest.sh just with header and license) and
                "skelX" (custom skeletons saved in user preferences)."""
        self.skeletons = parseString("""
    <skeletons>
        <skeleton name="beakerlib">
            # Include Beaker environment
            . /usr/bin/rhts-environment.sh || exit 1
            . /usr/share/beakerlib/beakerlib.sh || exit 1

            PACKAGE="<package/>"

            rlJournalStart
                rlPhaseStartSetup
                    rlAssertRpm $PACKAGE
                    rlRun "TmpDir=\$(mktemp -d)" 0 "Creating tmp directory"
                    rlRun "pushd $TmpDir"
                rlPhaseEnd

                rlPhaseStartTest
                    rlRun "touch foo" 0 "Creating the foo test file"
                    rlAssertExists "foo"
                    rlRun "ls -l foo" 0 "Listing the foo test file"
                rlPhaseEnd

                rlPhaseStartCleanup
                    rlRun "popd"
                    rlRun "rm -r $TmpDir" 0 "Removing tmp directory"
                rlPhaseEnd
            rlJournalPrintText
            rlJournalEnd
        </skeleton>
        <skeleton name="beaker">
            # Include Beaker environment
            . /usr/bin/rhts-environment.sh || exit 1

            PACKAGE="<package/>"
            set -x

            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #   Setup
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            score=0
            rpm -q $PACKAGE || ((score++))
            TmpDir=$(mktemp -d) || ((score++))
            pushd $TmpDir || ((score++))
            ((score == 0)) &amp;&amp; result=PASS || result=FAIL
            echo "Setup finished, result: $result, score: $score"
            report_result $TEST/setup $result $score


            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #   Test
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            score=0
            touch foo || ((score++))
            [ -e foo ] || ((score++))
            ls -l foo || ((score++))
            ((score == 0)) &amp;&amp; result=PASS || result=FAIL
            echo "Testing finished, result: $result, score: $score"
            report_result $TEST/testing $result $score


            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #   Cleanup
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            score=0
            popd || ((score++))
            rm -r "$TmpDir" || ((score++))
            ((score == 0)) &amp;&amp; result=PASS || result=FAIL
            echo "Cleanup finished, result: $result, score: $score"
            report_result $TEST/cleanup $result $score
        </skeleton>
        <skeleton name="multihost">
            # Include Beaker environment
            . /usr/bin/rhts-environment.sh || exit 1
            . /usr/share/beakerlib/beakerlib.sh || exit 1

            PACKAGE="<package/>"

            # set client &amp; server manually if debugging
            # SERVERS="server.example.com"
            # CLIENTS="client.example.com"

            Server() {
                rlPhaseStartTest Server
                    # server setup goes here
                    rlRun "rhts-sync-set -s READY" 0 "Server ready"
                    rlRun "rhts-sync-block -s DONE $CLIENTS" 0 "Waiting for the client"
                rlPhaseEnd
            }

            Client() {
                rlPhaseStartTest Client
                    rlRun "rhts-sync-block -s READY $SERVERS" 0 "Waiting for the server"
                    # client action goes here
                    rlRun "rhts-sync-set -s DONE" 0 "Client done"
                rlPhaseEnd
            }

            rlJournalStart
                rlPhaseStartSetup
                    rlAssertRpm $PACKAGE
                    rlLog "Server: $SERVERS"
                    rlLog "Client: $CLIENTS"
                    rlRun "TmpDir=\$(mktemp -d)" 0 "Creating tmp directory"
                    rlRun "pushd $TmpDir"
                rlPhaseEnd

                if echo $SERVERS | grep -q $HOSTNAME ; then
                    Server
                elif echo $CLIENTS | grep -q $HOSTNAME ; then
                    Client
                else
                    rlReport "Stray" "FAIL"
                fi

                rlPhaseStartCleanup
                    rlRun "popd"
                    rlRun "rm -r $TmpDir" 0 "Removing tmp directory"
                rlPhaseEnd
            rlJournalPrintText
            rlJournalEnd
        </skeleton>
        <skeleton name="simple">
            rhts-run-simple-test $TEST ./test
        </skeleton>
        <skeleton name="empty">
        </skeleton>
    </skeletons>
            """)

        self.makefile = """
            export TEST=%s
            export TESTVERSION=%s

            BUILT_FILES=

            FILES=$(METADATA) %s

            .PHONY: all install download clean

            run: $(FILES) build
            	./runtest.sh

            build: $(BUILT_FILES)%s

            clean:
            	rm -f *~ $(BUILT_FILES)


            include /usr/share/rhts/lib/rhts-make.include

            $(METADATA): Makefile
            	@echo "Owner:           %s" > $(METADATA)
            	@echo "Name:            $(TEST)" >> $(METADATA)
            	@echo "TestVersion:     $(TESTVERSION)" >> $(METADATA)
            	@echo "Path:            $(TEST_DIR)" >> $(METADATA)%s

            	rhts-lint $(METADATA)
            """

        self.list = []
        self.list.extend(findNodeNames(self.skeletons, "skeleton"))
        self.list.extend(findNodeNames(self.options.pref.skeletons, "skeleton"))
        self.common = False
        self.default(self.options.skeleton())

    def replaceVariables(self, xml, test = None):
        """ Replace all <variable> tags with their respective values """
        skeleton = ""
        for child in xml.childNodes:
            # regular text node -> just copy
            if child.nodeType == child.TEXT_NODE:
                skeleton += child.nodeValue
            # xml tag -> try to expand value of test.tag.show()
            elif child.nodeType == child.ELEMENT_NODE:
                try:
                    name = child.tagName
                    # some variables need a special treatment
                    if name == "test":
                        value = test.fullPath()
                    elif name == "bugs":
                        value = test.testname.bugs.show()
                    elif name == "reproducers":
                        value = test.testname.bugs.reproducers.show()
                    else:
                        # map long names to the real vars
                        map = {
                            "description" : "desc",
                            "architectures" : "archs",
                        }
                        try: name = map[name]
                        except: pass
                        # get the value
                        value = eval("test." + name + ".show()")
                except:
                    # leave unknown xml tags as they are
                    skeleton += child.toxml('utf-8')
                else:
                    skeleton += value
        return skeleton

    def getRuntest(self, test = None):
        """ Return runtest.sh skeleton corresponding to user choice """
        # get the template from predefined or user skeletons
        skeleton = findNode(self.skeletons, "skeleton", self.data) \
                or findNode(self.options.pref.skeletons, "skeleton", self.data)
        # substitute variables, convert to plain text
        skeleton = self.replaceVariables(skeleton, test)
        # return dedented skeleton without trailing whitespace
        skeleton = re.sub("\n\s+$", "\n", skeleton)
        return dedentText(skeleton)

    def getMakefile(self, testname, version, author, reproducers, meta):
        """ Return Makefile skeleton """
        files = ["runtest.sh", "Makefile", "PURPOSE"]
        build = ["runtest.sh"]
        # add "test" file when creating simple test
        if self.data == "simple":
            files.append("test")
            build.append("test")
        # include the reproducers in the lists as well
        if reproducers:
            for reproducer in reproducers:
                files.append(reproducer)
                # add script-like reproducers to build tag
                if RegExpScript.search(reproducer):
                    build.append(reproducer)
        chmod = "\n            	test -x %s || chmod a+x %s"
        return dedentText(self.makefile % (testname, version, " ".join(files),
                "".join([chmod % (file, file) for file in build]), author, meta))

    def getVimHeader(self):
        """ Insert the vim completion header if it's an beakerlib skeleton """
        if re.search("rl[A-Z]", self.getRuntest()):
            return comment(VimDictionary,
                    top = False, bottom = False, padding = 0) + "\n"
        else:
            return ""


class Author(Inquisitor):
    """ Author's name """

    def init(self):
        self.name = "Author"
        self.question = "Author's name"
        self.description = """Put your name [middle name] and surname here,
                abbreviations allowed."""
        # ask for author when run for the first time
        self.common = self.options.pref.firstRun
        self.default(self.options.author())

    def valid(self):
        return self.data is not None \
            and RegExpAuthor.match(self.data)


class Email(Inquisitor):
    """ Author's email """

    def init(self):
        self.name = "Email"
        self.question = "Author's email"
        self.description = """Email address in lower case letters,
                dots and dashes. Underscore allowed before the "@" only."""
        # ask for author when run for the first time
        self.common = self.options.pref.firstRun
        self.default(self.options.email())

    def valid(self):
        return self.data is not None \
            and RegExpEmail.match(self.data)


class Desc(Inquisitor):
    """ Description """

    def init(self):
        self.name = "Description"
        self.question = "Short description"
        self.description = "Provide a short sentence describing the test."
        self.default(self.options.desc())

    def valid(self):
        return self.data is not None and self.data not in ["", "?"]


class Test(SingleChoice):
    """ Test class containing all the information necessary for building a test """

    def init(self):
        self.name = "Test fields"
        if self.options.makefile:
            self.question = "Ready to write the new Makefile, "\
                    "please review or make the changes"
        else:
            self.question = "Ready to create the test, please review"
        self.description = "Type a few letters from field name to "\
                "edit or press ENTER to confirm. Use the \"write\" keyword "\
                "to save current settings as preferences."
        self.list = []
        self.default(["", "Everything OK"])

        # possibly print first time welcome message
        if self.options.pref.firstRun:
            print dedentText("""
                Welcome to The Beaker Wizard!
                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                It seems, you're running the beaker-wizard for the first time.
                I'll try to be a little bit more verbose. Should you need
                any help in the future, just try using the "?" character.
                """, count = 16)

        # gather all test data
        self.testname = Name(self.options)
        self.path = Path(self.options)
        self.type = Type(self.options, suggest = self.testname.bugs.suggestType())
        self.package = Package(self.options,
                suggest = self.testname.bugs.getComponent())
        self.namespace = Namespace(self.options)
        self.desc = Desc(self.options,
                suggest = self.testname.bugs.suggestDescription())

        self.runfor = RunFor(self.options, suggest = self.package.value())
        self.requires = Requires(self.options, suggest = self.package.value())
        self.archs = Architectures(self.options)
        self.releases = Releases(self.options)
        self.time = Time(self.options)

        self.version = Version(self.options)
        self.priority = Priority(self.options)
        self.confidential = Confidential(self.options,
                suggest = self.testname.bugs.suggestConfidential())
        self.destructive = Destructive(self.options)
        self.license = License(self.options)

        self.skeleton = Skeleton(self.options,
                suggest = self.type.suggestSkeleton())
        self.author = Author(self.options)
        self.email = Email(self.options)

        # we escape review only in force mode
        if not self.options.force(): self.confirm = True
        if not self.confirm: self.format()

    def valid(self):
        return self.data is not None \
            and self.data not in ["?"] \
            and self.edit(checkOnly = True)

    def format(self):
        """ Format all test fields into nice table """
        print
        print self.fullPath()
        print
        self.namespace.format()
        self.package.format()
        self.type.format()
        self.path.format()
        self.testname.format()
        self.desc.format()
        print
        self.testname.bugs.format()
        if not self.options.makefile: # skip in makefile edit mode
            self.testname.prefix.format()
            self.testname.bugs.reproducers.format()
        print
        self.runfor.format()
        self.requires.format()
        self.archs.format()
        self.releases.format()
        self.version.format()
        self.time.format()
        print
        self.priority.format()
        self.license.format()
        self.confidential.format()
        self.destructive.format()
        print
        if not self.options.makefile:
            self.skeleton.format() # irrelevant in makefile edit mode
        self.author.format()
        self.email.format()
        print

    def heading(self):
        SingleChoice.heading(self)
        self.format()

    def edit(self, checkOnly = False):
        """ Edit test fields (based on just few letters from field name)
        If checkOnly is on then checks only for valid field name """

        # quit
        if re.match("q|exit", self.data, re.I):
            print "Ok, quitting for now. See you later ;-)"
            sys.exit(0)
        # no (seems the user is beginner -> turn on verbosity)
        elif re.match("no?$", self.data, re.I):
            self.options.opt.verbose = True
            return True
        # yes
        elif RegExpYes.match(self.data):
            return True

        # check all fields for matching string (and edit if not checking only)
        for field in self.testname, self.package, self.namespace, self.runfor, \
                self.requires, self.package, self.releases, self.version, \
                self.time, self.desc, self.destructive, self.archs, \
                self.path, self.priority, self.confidential, self.license, \
                self.skeleton, self.author, self.email, self.testname.prefix, \
                self.testname.bugs.reproducers:
            if field.matchName(self.data):
                if not checkOnly: field.edit()
                return True

        # bugs & type have special treatment
        if self.type.matchName(self.data):
            if not checkOnly and self.type.edit():
                # if type has changed suggest a new skeleton
                self.skeleton = Skeleton(self.options,
                        suggest = self.type.suggestSkeleton())
            return True
        elif self.testname.bugs.matchName(self.data):
            if not checkOnly and self.testname.bugs.edit():
                # if bugs changed, suggest new name & desc & reproducers
                if self.testname.bugs.fetchBugDetails():
                    self.testname.edit(self.testname.bugs.suggestTestName())
                    self.desc.edit(self.testname.bugs.suggestDescription())
                    self.testname.bugs.reproducers.edit()
            return True
        # write preferences
        elif re.match("w", self.data, re.I):
            if not checkOnly:
                self.savePreferences(force = True)
            return True
        # bad option
        else:
            return False

    def relativePath(self):
        """ Return relative path from package directory"""
        return "%s%s/%s" % (
                self.type.value(),
                self.path.value(),
                self.testname.value())

    def fullPath(self):
        """ Return complete test path """
        return "/%s/%s/%s" % (
            self.namespace.value(),
            self.package.value(),
            self.relativePath())

    def formatAuthor(self):
        """ Format author with email """
        return "%s <%s>" % (self.author.value(), self.email.value())

    def formatHeader(self, filename):
        """ Format standard header """
        return "%s of %s\nDescription: %s\nAuthor: %s" % (
            filename, self.fullPath(),
            self.desc.value(),
            self.formatAuthor())

    def formatMakefile(self):
        return (
            comment(self.formatHeader("Makefile")) + "\n" +
            comment(self.license.get(), top = False) + "\n" +
            self.skeleton.getMakefile(
                self.fullPath(),
                self.version.value(),
                self.formatAuthor(),
                self.testname.bugs.reproducers.value(),
                self.desc.formatMakefileLine() +
                self.type.formatMakefileLine(name = "Type") +
                self.time.formatMakefileLine(name = "TestTime") +
                self.runfor.formatMakefileLine(name = "RunFor") +
                self.requires.formatMakefileLine(name = "Requires") +
                self.priority.formatMakefileLine() +
                self.license.formatMakefileLine() +
                self.confidential.formatMakefileLine() +
                self.destructive.formatMakefileLine() +
                self.testname.bugs.formatMakefileLine(name = "Bug") +
                self.releases.formatMakefileLine() +
                self.archs.formatMakefileLine()))

    def savePreferences(self, force = False):
        """ Save user preferences (well, maybe :-) """
        # update user preferences with current settings
        self.options.pref.update(
            self.author.value(),
            self.email.value(),
            self.options.confirm(),
            self.type.value(),
            self.namespace.value(),
            self.time.value(),
            self.priority.value(),
            self.confidential.value(),
            self.destructive.value(),
            self.testname.prefix.value(),
            self.license.value(),
            self.skeleton.value())
        # and possibly save them to disk
        if force or self.options.pref.firstRun or self.options.write():
            self.options.pref.save()

    def createFile(self, filename, content, mode=None):
        """ Create single test file with specified content """
        fullpath = self.relativePath() + "/" + filename
        addedToGit = ""

        # overwrite existing?
        if os.path.exists(fullpath):
            sys.stdout.write(fullpath + " already exists, ")
            if self.options.force():
                print "force on -> overwriting"
            else:
                sys.stdout.write("overwrite? [y/n] ")
                answer = unicode(sys.stdin.readline(), "utf-8")
                if not re.match("y", answer, re.I):
                    print "Ok skipping. Next time use -f if you want to overwrite files."
                    return

        # let's write it
        try:
            file = open(fullpath, "w")
            file.write(content.encode("utf-8"))
            file.close()

            # change mode if provided
            if mode: os.chmod(fullpath, mode)

            # and, optionally, add to Git
            if self.options.opt.git:
                addToGit(fullpath)
                addedToGit = ", added to git"
        except IOError:
            print "Cannot write to %s" % fullpath
            sys.exit(3)
        else:
            print "File", fullpath, "written" + addedToGit

    def create(self):
        """ Create all necessary test files """
        # if in the Makefile edit mode, just save the Makefile
        if self.options.makefile:
            self.options.makefile.save(self.fullPath(), self.version.value(),
                    self.formatMakefile())
            return

        # set file vars
        test = self.testname.value()
        path = self.relativePath()
        fullpath = self.fullPath()
        addedToGit = ""

        # create test directory
        class AlreadyExists(Exception): pass
        try:
            # nothing to do if already exists
            if os.path.isdir(path):
                raise AlreadyExists
            # otherwise attempt to create the whole hiearchy
            else:
                os.makedirs(path)
        except OSError, e:
            print "Bad, cannot create test directory %s :-(" % path
            sys.exit(1)
        except AlreadyExists:
            print "Well, directory %s already exists, let's see..." % path
        else:
            print "Directory %s created%s" % (path, addedToGit)

        # PURPOSE
        self.createFile("PURPOSE", content =
            self.formatHeader("PURPOSE") + "\n" +
            self.testname.bugs.formatBugDetails())

        # runtest.sh
        self.createFile("runtest.sh", content =
            "#!/bin/bash\n" +
            self.skeleton.getVimHeader() +
            comment(self.formatHeader("runtest.sh")) + "\n" +
            comment(self.license.get(), top = False) + "\n" +
            self.skeleton.getRuntest(self),
            mode=0755
            )

        # Makefile
        self.createFile("Makefile", content = self.formatMakefile())

        # test
        if self.skeleton.value() == "simple":
            self.createFile("test", content = "")

        # download reproducers
        self.testname.bugs.reproducers.download(self.relativePath())


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#   Main
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if __name__ == '__main__':
    # parse options and user preferences
    options = Options()

    # possibly display help or version message
    Help(options)

    # ask for all necessary details
    test = Test(options)

    # keep asking until everything is OK
    while not RegExpYes.match(test.value()):
        test.edit()
        test.default(["", "Everything OK"])
        test.ask(force = True)

    # and finally create the test file structure
    test.create()
    test.savePreferences()