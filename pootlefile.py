#!/usr/bin/env python

"""manages po files and their associated files"""

from translate.storage import po
from translate.misc import quote
from translate.filters import checks
from translate.convert import po2csv
from translate.convert import po2xliff
from translate.convert import pot2po
from translate.tools import pocompile
from jToolkit import timecache
import time
import os

def getmodtime(filename, default=None):
  """gets the modificationtime of the given file"""
  if os.path.exists(filename):
    return os.stat(filename)[os.path.stat.ST_MTIME]
  else:
    return default

def wordcount(unquotedstr):
  """returns the number of words in an unquoted str"""
  return len(unquotedstr.split())

class pootleelement(po.poelement, object):
  """a poelement with helpful methods for pootle"""
  def getunquotedmsgid(self, joinwithlinebreak=True):
    """returns the msgid as a list of unquoted strings (one per plural form present)"""
    msgid = [po.unquotefrompo(self.msgid, joinwithlinebreak)]
    if self.hasplural():
      msgid += [po.unquotefrompo(self.msgid_plural, joinwithlinebreak)]
    return msgid

  unquotedmsgid = property(getunquotedmsgid)

  def getunquotedmsgstr(self, joinwithlinebreak=True):
    """returns the msgstr as a list of unquoted strings (one per plural form present)"""
    if self.hasplural():
      msgstr = []
      for i in range(len(self.msgstr)):
        msgstr.append(po.unquotefrompo(self.msgstr[i], joinwithlinebreak))
    else:
      msgstr = [po.unquotefrompo(self.msgstr, joinwithlinebreak)]
    return msgstr

  def setunquotedmsgstr(self, text):
    """quotes text in po-style"""
    if isinstance(text, dict):
      quotedtext = {}
      for pluralid in text:
        pluraltext = text[pluralid].replace("\r\n", "\n")
        quotedtext[pluralid] = po.quoteforpo(pluraltext)
      self.msgstr = quotedtext
    else:
      text = text.replace("\r\n", "\n")
      self.msgstr = po.quoteforpo(text)

  unquotedmsgstr = property(getunquotedmsgstr, setunquotedmsgstr)

  def classify(self, checker):
    """returns all classify keys that this element should match, using the checker"""
    classes = ["total"]
    if self.isfuzzy():
      classes.append("fuzzy")
    if self.isblankmsgstr():
      classes.append("blank")
    if not ("fuzzy" in classes or "blank" in classes):
      classes.append("translated")
    # TODO: we don't handle checking plurals at all yet, as this is tricky...
    unquotedid = self.unquotedmsgid[0]
    unquotedstr = self.unquotedmsgstr[0]
    if isinstance(unquotedid, str) and isinstance(unquotedstr, unicode):
      unquotedid = unquotedid.decode("utf-8")
    failures = checker.run_filters(self, unquotedid, unquotedstr)
    for failure in failures:
      functionname = failure.split(":",2)[0]
      classes.append("check-" + functionname)
    return classes

class pootlefile(po.pofile):
  """this represents a pootle-managed .po file and its associated files"""
  def __init__(self, project, pofilename):
    po.pofile.__init__(self, elementclass=pootleelement)
    self.project = project
    self.checker = self.project.checker
    self.pofilename = pofilename
    self.filename = os.path.join(self.project.podir, self.pofilename)
    self.statsfilename = self.filename + os.extsep + "stats"
    self.pendingfilename = self.filename + os.extsep + "pending"
    self.assignsfilename = self.filename + os.extsep + "assigns"
    self.pendingfile = None
    # we delay parsing until it is required
    self.pomtime = None
    self.getstats()
    self.getassigns()
    self.tracker = timecache.timecache(20*60)

  def track(self, item, message):
    """sets the tracker message for the given item"""
    self.tracker[item] = message

  def readpofile(self):
    """reads and parses the main po file"""
    # make sure encoding is reset so it is read from the file
    self.encoding = None
    self.poelements = []
    pomtime = getmodtime(self.filename)
    self.parse(open(self.filename, 'r'))
    # we ignore all the headers by using this filtered set
    self.transelements = [poel for poel in self.poelements if not (poel.isheader() or poel.isblank())]
    self.classifyelements()
    self.pomtime = pomtime

  def savepofile(self):
    """saves changes to the main file to disk..."""
    lines = self.tolines()
    open(self.filename, "w").writelines(lines)
    # don't need to reread what we saved
    self.pomtime = getmodtime(self.filename)

  def pofreshen(self):
    """makes sure we have a freshly parsed pofile"""
    if not os.path.exists(self.filename):
      # the file has been removed, update the project index (and fail below)
      self.project.scanpofiles()
    if self.pomtime != getmodtime(self.filename):
      self.readpofile()

  def getsource(self):
    """returns pofile source"""
    self.pofreshen()
    lines = self.tolines()
    return "".join(lines)

  def getcsv(self):
    """returns pofile as csv"""
    self.pofreshen()
    convertor = po2csv.po2csv()
    csvfile = convertor.convertfile(self)
    lines = csvfile.tolines()
    return "".join(lines)

  def getxliff(self):
    """returns pofile as xliff"""
    self.pofreshen()
    convertor = po2xliff.po2xliff()
    xlifffile = convertor.convertfile(self, None)
    return xlifffile

  def getmo(self):
    """returns pofile compiled into mo"""
    self.pofreshen()
    convertor = pocompile.pocompile()
    mofile = convertor.convertfile(self)
    return mofile

  def readpendingfile(self):
    """reads and parses the pending file corresponding to this po file"""
    if os.path.exists(self.pendingfilename):
      pendingmtime = getmodtime(self.pendingfilename)
      if pendingmtime == getattr(self, "pendingmtime", None):
        return
      inputfile = open(self.pendingfilename, "r")
      self.pendingmtime, self.pendingfile = pendingmtime, po.pofile(inputfile, elementclass=self.elementclass)
      if self.pomtime:
        self.reclassifysuggestions()
    else:
      self.pendingfile = po.pofile(elementclass=self.elementclass)
      self.savependingfile()

  def savependingfile(self):
    """saves changes to disk..."""
    lines = self.pendingfile.tolines()
    open(self.pendingfilename, "w").writelines(lines)
    self.pendingmtime = getmodtime(self.pendingfilename)

  def getstats(self):
    """reads the stats if neccessary or returns them from the cache"""
    if os.path.exists(self.statsfilename):
      try:
        self.readstats()
      except Exception, e:
        print "Error reading stats from %s, so recreating (Error was %s)" % (self.statsfilename, e)
        raise
        self.statspomtime = None
    pomtime = getmodtime(self.filename)
    pendingmtime = getmodtime(self.pendingfilename, None)
    if hasattr(self, "pendingmtime"):
      self.readpendingfile()
    if pomtime != getattr(self, "statspomtime", None) or pendingmtime != getattr(self, "statspendingmtime", None):
      self.calcstats()
      self.savestats()
    return self.stats

  def readstats(self):
    """reads the stats from the associated stats file, setting the required variables"""
    statsmtime = getmodtime(self.statsfilename)
    if statsmtime == getattr(self, "statsmtime", None):
      return
    stats = open(self.statsfilename, "r").read()
    mtimes, postatsstring = stats.split("\n", 1)
    mtimes = mtimes.strip().split()
    if len(mtimes) == 1:
      frompomtime = int(mtimes[0])
      frompendingmtime = None
    elif len(mtimes) == 2:
      frompomtime = int(mtimes[0])
      frompendingmtime = int(mtimes[1])
    postats = {}
    msgidwordcounts = []
    msgstrwordcounts = []
    for line in postatsstring.split("\n"):
      if not line.strip():
        continue
      if not ":" in line:
        print "invalid stats line in", self.statsfilename,line
        continue
      name, items = line.split(":", 1)
      if name == "msgidwordcounts":
        msgidwordcounts = [[int(subitem.strip()) for subitem in item.strip().split("/")] for item in items.strip().split(",") if item]
      elif name == "msgstrwordcounts":
        msgstrwordcounts = [[int(subitem.strip()) for subitem in item.strip().split("/")] for item in items.strip().split(",") if item]
      else:
        items = [int(item.strip()) for item in items.strip().split(",") if item]
        postats[name.strip()] = items
    # save all the read times, data simultaneously
    self.statspomtime, self.statspendingmtime, self.statsmtime, self.stats, self.msgidwordcounts, self.msgstrwordcounts = frompomtime, frompendingmtime, statsmtime, postats, msgidwordcounts, msgstrwordcounts
    # if in old-style format (counts instead of items), recalculate
    totalitems = postats.get("total", [])
    if len(totalitems) == 1 and totalitems[0] != 0:
      self.calcstats()
      self.savestats()
    if (len(msgidwordcounts) < len(totalitems)) or (len(msgstrwordcounts) < len(totalitems)):
      self.pofreshen()
      self.countwords()
      self.savestats()

  def savestats(self):
    """saves the current statistics to file"""
    # assumes self.stats is up to date
    try:
      postatsstring = "\n".join(["%s:%s" % (name, ",".join(map(str,items))) for name, items in self.stats.iteritems()])
      wordcountsstring = "msgidwordcounts:" + ",".join(["/".join(map(str,subitems)) for subitems in self.msgidwordcounts])
      wordcountsstring += "\nmsgstrwordcounts:" + ",".join(["/".join(map(str,subitems)) for subitems in self.msgstrwordcounts])
      statsfile = open(self.statsfilename, "w")
      if os.path.exists(self.pendingfilename):
        statsfile.write("%d %d\n" % (getmodtime(self.filename), getmodtime(self.pendingfilename)))
      else:
        statsfile.write("%d\n" % getmodtime(self.filename))
      statsfile.write(postatsstring + "\n" + wordcountsstring)
      statsfile.close()
    except IOError:
      # TODO: log a warning somewhere. we don't want an error as this is an optimization
      pass

  def calcstats(self):
    """calculates translation statistics for the given po file"""
    self.pofreshen()
    postats = dict([(name, items) for name, items in self.classify.iteritems()])
    self.stats = postats

  def getassigns(self):
    """reads the assigns if neccessary or returns them from the cache"""
    if os.path.exists(self.assignsfilename):
      self.assigns = self.readassigns()
    else:
      self.assigns = {}
    return self.assigns

  def readassigns(self):
    """reads the assigns from the associated assigns file, returning the assigns
    the format is a number of lines consisting of
    username: action: itemranges
    where itemranges is a comma-separated list of item numbers or itemranges like 3-5
    e.g.  pootlewizz: review: 2-99,101"""
    assignsmtime = getmodtime(self.assignsfilename)
    if assignsmtime == getattr(self, "assignsmtime", None):
      return
    assignsstring = open(self.assignsfilename, "r").read()
    poassigns = {}
    for line in assignsstring.split("\n"):
      if not line.strip():
        continue
      if not line.count(":") == 2:
        print "invalid assigns line in", self.assignsfilename, line
        continue
      username, action, itemranges = line.split(":", 2)
      username, action = username.strip(), action.strip()
      if not username in poassigns:
        poassigns[username] = {}
      userassigns = poassigns[username]
      if not action in userassigns:
        userassigns[action] = []
      items = userassigns[action]
      for itemrange in itemranges.split(","):
        if "-" in itemrange:
          if not line.count("-") == 1:
            print "invalid assigns range in", self.assignsfilename, line, itemrange
            continue
          itemstart, itemstop = [int(item.strip()) for item in itemrange.split("-", 1)]
          items.extend(range(itemstart, itemstop+1))
        else:
          item = int(itemrange.strip())
          items.append(item)
      userassigns[action] = items
    return poassigns

  def assignto(self, item, username, action):
    """assigns the item to the given username for the given action"""
    userassigns = self.assigns.setdefault(username, {})
    items = userassigns.setdefault(action, [])
    if item not in items:
      items.append(item)
    self.saveassigns()

  def unassign(self, item, username, action=None):
    """removes assignments of the item to the given username for the given action (or all actions)"""
    userassigns = self.assigns.setdefault(username, {})
    if action is None:
      itemlist = [userassigns.get(action, []) for action in userassigns]
    else:
      itemlist = [userassigns.get(action, [])]
    for items in itemlist:
      if item in items:
        items.remove(item)
    self.saveassigns()

  def saveassigns(self):
    """saves the current assigns to file"""
    # assumes self.assigns is up to date
    assignstrings = []
    usernames = self.assigns.keys()
    usernames.sort()
    for username in usernames:
      actions = self.assigns[username].keys()
      actions.sort()
      for action in actions:
        items = self.assigns[username][action]
        items.sort()
        if items:
          lastitem = None
          rangestart = None
          assignstring = "%s: %s: " % (username, action)
          for item in items:
            if item - 1 == lastitem:
              if rangestart is None:
                rangestart = lastitem
            else:
              if rangestart is not None:
                assignstring += "-%d" % lastitem
                rangestart = None
              if lastitem is None:
                assignstring += "%d" % item
              else:
                assignstring += ",%d" % item
            lastitem = item
          if rangestart is not None:
            assignstring += "-%d" % lastitem
          assignstrings.append(assignstring + "\n")
    assignsfile = open(self.assignsfilename, "w")
    assignsfile.writelines(assignstrings)
    assignsfile.close()

  def setmsgstr(self, item, newmsgstr, userprefs, languageprefs):
    """updates a translation with a new msgstr value"""
    self.pofreshen()
    thepo = self.transelements[item]
    thepo.unquotedmsgstr = newmsgstr
    thepo.markfuzzy(False)
    self.updateheader(add=True, PO_Revision_Date = time.strftime("%F %H:%M%z"))
    if userprefs:
      if getattr(userprefs, "name", None) and getattr(userprefs, "email", None):
        self.updateheader(add=True, Last_Translator = "%s <%s>" % (userprefs.name, userprefs.email))
    if languageprefs:
      nplurals = getattr(languageprefs, "nplurals", None)
      pluralequation = getattr(languageprefs, "pluralequation", None)
      if nplurals and pluralequation:
        self.updateheaderplural(nplurals, pluralequation)
    self.savepofile()
    self.reclassifyelement(item)

  def classifyelements(self):
    """makes a dictionary of which elements fall into which classifications"""
    self.classify = {}
    self.classify["fuzzy"] = []
    self.classify["blank"] = []
    self.classify["translated"] = []
    self.classify["has-suggestion"] = []
    self.classify["total"] = []
    for checkname in self.checker.getfilters().keys():
      self.classify["check-" + checkname] = []
    for item, poel in enumerate(self.transelements):
      classes = poel.classify(self.checker)
      if self.getsuggestions(item):
        classes.append("has-suggestion")
      for classname in classes:
        if classname in self.classify:
          self.classify[classname].append(item)
        else:
          self.classify[classname] = item
    self.countwords()

  def countwords(self):
    """counts the words in each of the elements"""
    self.msgidwordcounts = []
    self.msgstrwordcounts = []
    for poel in self.transelements:
      self.msgidwordcounts.append([wordcount(text) for text in poel.unquotedmsgid])
      self.msgstrwordcounts.append([wordcount(text) for text in poel.unquotedmsgstr])

  def reclassifyelement(self, item):
    """updates the classification of poel in self.classify"""
    poel = self.transelements[item]
    self.msgidwordcounts[item] = [wordcount(text) for text in poel.unquotedmsgid]
    self.msgstrwordcounts[item] = [wordcount(text) for text in poel.unquotedmsgstr]
    classes = poel.classify(self.checker)
    if self.getsuggestions(item):
      classes.append("has-suggestion")
    for classname, matchingitems in self.classify.items():
      if (classname in classes) != (item in matchingitems):
        if classname in classes:
          self.classify[classname].append(item)
        else:
          self.classify[classname].remove(item)
        self.classify[classname].sort()
    self.calcstats()
    self.savestats()

  def reclassifysuggestions(self):
    """shortcut to only update classification of has-suggestion for all items"""
    suggitems = []
    suggsources = {}
    for thesugg in self.pendingfile.poelements:
      sources = tuple(thesugg.getsources())
      suggsources[sources] = thesugg
    suggitems = [item for item in self.transelements if tuple(item.getsources()) in suggsources]
    havesuggestions = self.classify["has-suggestion"]
    for item, poel in enumerate(self.transelements):
      if (poel in suggitems) != (item in havesuggestions):
        if poel in suggitems:
          havesuggestions.append(item)
        else:
          havesuggestions.remove(item)
        havesuggestions.sort()
    self.calcstats()
    self.savestats()

  def getsuggestions(self, item):
    """find all the suggestion items submitted for the given (pofile or pofilename) and item"""
    self.readpendingfile()
    thepo = self.transelements[item]
    sources = thepo.getsources()
    # TODO: review the matching method
    suggestpos = [suggestpo for suggestpo in self.pendingfile.poelements if suggestpo.getsources() == sources]
    return suggestpos

  def addsuggestion(self, item, suggmsgstr, username):
    """adds a new suggestion for the given item to the pendingfile"""
    self.readpendingfile()
    thepo = self.transelements[item]
    newpo = thepo.copy()
    if username is not None:
      newpo.msgidcomments.append('"_: suggested by %s"' % username)
    newpo.unquotedmsgstr = suggmsgstr
    newpo.markfuzzy(False)
    self.pendingfile.poelements.append(newpo)
    self.savependingfile()
    self.reclassifyelement(item)

  def deletesuggestion(self, item, suggitem):
    """removes the suggestion from the pending file"""
    self.readpendingfile()
    thepo = self.transelements[item]
    sources = thepo.getsources()
    # TODO: remove the suggestion in a less brutal manner
    pendingitems = [pendingitem for pendingitem, suggestpo in enumerate(self.pendingfile.poelements) if suggestpo.getsources() == sources]
    pendingitem = pendingitems[suggitem]
    del self.pendingfile.poelements[pendingitem]
    self.savependingfile()
    self.reclassifyelement(item)

  def iteritems(self, search, lastitem=None):
    """iterates through the items in this pofile starting after the given lastitem, using the given search"""
    # update stats if required
    self.getstats()
    if lastitem is None:
      minitem = 0
    else:
      minitem = lastitem + 1
    maxitem = len(self.transelements)
    validitems = range(minitem, maxitem)
    if search.assignedto or search.assignedaction: 
      # filter based on assign criteria
      self.getassigns()
      if search.assignedto:
        usernames = [search.assignedto]
      else:
        usernames = self.assigns.iterkeys()
      assignitems = []
      for username in usernames:
        if search.assignedaction:
          actionitems = self.assigns[username].get(search.assignedaction, [])
          assignitems.extend(actionitems)
        else:
          for actionitems in self.assigns[username].itervalues():
            assignitems.extend(actionitems)
      validitems = [item for item in validitems if item in assignitems]
    # loop through, filtering on matchnames if required
    for item in validitems:
      if not search.matchnames:
        yield item
      for name in search.matchnames:
        if item in self.classify[name]:
          yield item

  def matchitems(self, newpofile, usesources=False):
    """matches up corresponding items in this pofile with the given newpofile, and returns tuples of matching poitems (None if no match found)"""
    if not hasattr(self, "msgidindex"):
      self.makeindex()
    if not hasattr(newpofile, "msgidindex"):
      newpofile.makeindex()
    matches = []
    for newpo in newpofile.poelements:
      foundsource = False
      if usesources:
        newsources = newpo.getsources()
        mergedsources = []
        for source in newsources:
          if source in mergedsources:
            continue
          if source in self.sourceindex:
            oldpo = self.sourceindex[source]
            if oldpo is not None:
              foundsource = True
              matches.append((oldpo, newpo))
              mergedsources.append(source)
              continue
      if not foundsource:
        msgid = po.getunquotedstr(newpo.msgid)
        if msgid in self.msgidindex:
          oldpo = self.msgidindex[msgid]
          matches.append((oldpo, newpo))
        else:
          matches.append((None, newpo))
    # find items that have been removed
    matcheditems = [oldpo for oldpo, newpo in matches if oldpo]
    for oldpo in self.poelements:
      if not oldpo in matcheditems:
        matches.append((oldpo, None))
    return matches

  def mergeitem(self, oldpo, newpo, username):
    """merges any changes from newpo into oldpo"""
    unchanged = po.unquotefrompo(oldpo.msgstr, False) == po.unquotefrompo(newpo.msgstr, False)
    if oldpo.isblankmsgstr() or newpo.isblankmsgstr() or oldpo.isheader() or newpo.isheader() or unchanged:
      oldpo.merge(newpo)
    else:
      for item, matchpo in enumerate(self.transelements):
        if matchpo == oldpo:
          self.addsuggestion(item, newpo.unquotedmsgstr, username)
          return
      raise KeyError("Could not find item for merge")

  def mergefile(self, newpofile, username, allownewstrings=True):
    """make sure each msgid is unique ; merge comments etc from duplicates into original"""
    self.makeindex()
    matches = self.matchitems(newpofile)
    for oldpo, newpo in matches:
      if oldpo is None:
        if allownewstrings:
          self.poelements.append(newpo)
      elif newpo is None:
        # TODO: mark the old one as obsolete
        pass
      else:
        self.mergeitem(oldpo, newpo, username)
        # we invariably want to get the sources from the newpo
        oldpo.sourcecomments = newpo.sourcecomments
    self.savepofile()
    # the easiest way to recalculate everythign
    self.readpofile()

class Search:
  """an object containint all the searching information"""
  def __init__(self, dirfilter=None, matchnames=[], assignedto=None, assignedaction=None, searchtext=None):
    self.dirfilter = dirfilter
    self.matchnames = matchnames
    self.assignedto = assignedto
    self.assignedaction = assignedaction
    self.searchtext = searchtext

