# -*- coding: utf-8 -*-

# Copyright (C) 2001-2004 Anthony Towns <ajt@debian.org>
#                         Andreas Barth <aba@debian.org>
#                         Fabio Tranchitella <kobold@debian.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from collections import defaultdict
import re

from britney2 import DependencyType
from britney2.policies.policy import PolicyVerdict

VERDICT2DESC = {
    PolicyVerdict.PASS:
        'Will attempt migration (Any information below is purely informational)',
    PolicyVerdict.PASS_HINTED:
        'Will attempt migration due to a hint (Any information below is purely informational)',
    PolicyVerdict.REJECTED_TEMPORARILY:
        'Waiting for test results, another package or too young (no action required now - check later)',
    PolicyVerdict.REJECTED_WAITING_FOR_ANOTHER_ITEM:
        'Waiting for another item to be ready to migrate (no action required now - check later)',
    PolicyVerdict.REJECTED_BLOCKED_BY_ANOTHER_ITEM:
        'BLOCKED: Cannot migrate due to another item, which is blocked (please check which dependencies are stuck)',
    PolicyVerdict.REJECTED_NEEDS_APPROVAL:
        'BLOCKED: Needs an approval (either due to a freeze, the source suite or a manual hint)',
    PolicyVerdict.REJECTED_CANNOT_DETERMINE_IF_PERMANENT:
        'BLOCKED: Maybe temporary, maybe blocked but Britney is missing information (check below or the buildds)',
    PolicyVerdict.REJECTED_PERMANENTLY:
        'BLOCKED: Rejected/introduces a regression',
}


class Excuse(object):
    """Excuse class

    This class represents an update excuse, which is a detailed explanation
    of why a package can or cannot be updated in the testing distribution from
    a newer package in another distribution (like for example unstable).

    The main purpose of the excuses is to be written in an HTML file which
    will be published over HTTP. The maintainers will be able to parse it
    manually or automatically to find the explanation of why their packages
    have been updated or not.
    """

    # @var reemail
    # Regular expression for removing the email address
    reemail = re.compile(r" *<.*?>")

    def __init__(self, name):
        """Class constructor

        This method initializes the excuse with the specified name and
        the default values.
        """
        self.name = name
        self.ver = ("-", "-")
        self.maint = None
        self.daysold = None
        self.mindays = None
        self.section = None
        self._is_valid = False
        self.needs_approval = False
        self.hints = []
        self.forced = False
        self._policy_verdict = PolicyVerdict.REJECTED_PERMANENTLY

        self.all_invalid_deps = set()
        self.all_deps = {}
        self.sane_deps = []
        self.break_deps = []
        self.unsatisfiable_on_archs = []
        self.unsat_deps = defaultdict(set)
        self.newbugs = set()
        self.oldbugs = set()
        self.reason = {}
        self.htmlline = []
        self.missing_builds = set()
        self.missing_builds_ood_arch = set()
        self.old_binaries = defaultdict(set)
        self.policy_info = {}

        self.bounty = {}
        self.penalty = {}

    def sortkey(self):
        if self.daysold is None:
            return (-1, self.name)
        return (self.daysold, self.name)

    @property
    def is_valid(self):
        return False if self._policy_verdict.is_rejected else True

    @property
    def policy_verdict(self):
        return self._policy_verdict

    @policy_verdict.setter
    def policy_verdict(self, value):
        if value.is_rejected and self.forced:
            # By virtue of being forced, the item was hinted to
            # undo the rejection
            value = PolicyVerdict.PASS_HINTED
        self._policy_verdict = value

    def set_vers(self, tver, uver):
        """Set the versions of the item from target and source suite"""
        if tver and uver:
            self.ver = (tver, uver)
        elif tver:
            self.ver = (tver, self.ver[1])
        elif uver:
            self.ver = (self.ver[0], uver)

    def set_maint(self, maint):
        """Set the package maintainer's name"""
        self.maint = self.reemail.sub("", maint)

    def set_section(self, section):
        """Set the section of the package"""
        self.section = section

    def add_dependency(self, deptype, name, arch):
        """Add a dependency of type deptype """
        if name not in self.all_deps:
            self.all_deps[name]={}
        if deptype not in self.all_deps[name]:
            self.all_deps[name][deptype]=[]
        self.all_deps[name][deptype].append(arch)

    def get_deps(self):
        # the autohinter uses the excuses data to query dependencies between
        # excuses. For now, we keep the current behaviour by just returning
        # the data that was in the old deps set
        """ Get the dependencies of type DEPENDS """
        deps = set()
        for dep in self.all_deps:
            if DependencyType.DEPENDS in self.all_deps[dep]:
                deps.add(dep)
        return deps

    def add_sane_dep(self, name):
        """Add a sane dependency"""
        if name not in self.sane_deps: self.sane_deps.append(name)

    def add_break_dep(self, name, arch):
        """Add a break dependency"""
        if (name, arch) not in self.break_deps:
            self.break_deps.append( (name, arch) )

    def add_unsatisfiable_on_arch(self,  arch):
        """Add an arch that has unsatisfiable dependencies"""
        if arch not in self.unsatisfiable_on_archs:
            self.unsatisfiable_on_archs.append(arch)

    def add_unsatisfiable_dep(self, signature, arch):
        """Add an unsatisfiable dependency"""
        self.unsat_deps[arch].add(signature)

    def invalidate_dependency(self, name):
        """Invalidate dependency"""
        self.all_invalid_deps.add(name)

    def setdaysold(self, daysold, mindays):
        """Set the number of days from the upload and the minimum number of days for the update"""
        self.daysold = daysold
        self.mindays = mindays

    def force(self):
        """Add force hint"""
        self.forced = True
        if self._policy_verdict.is_rejected:
            self._policy_verdict = PolicyVerdict.PASS_HINTED
            return True
        return False

    def addhtml(self, note):
        """Add a note in HTML"""
        self.htmlline.append(note)

    def missing_build_on_arch(self, arch):
        """Note that the item is missing a build on a given architecture"""
        self.missing_builds.add(arch)

    def missing_build_on_ood_arch(self, arch):
        """Note that the item is missing a build on a given "out of date" architecture"""
        self.missing_builds.add(arch)

    def add_old_binary(self, binary, from_source_version):
        """Denote than an old binary ("cruft") is available from a previous source version"""
        self.old_binaries[from_source_version].add(binary)

    def add_hint(self, hint):
        self.hints.append(hint)

    def _format_verdict_summary(self):
        verdict = self._policy_verdict
        if verdict in VERDICT2DESC:
            return VERDICT2DESC[verdict]
        return "UNKNOWN: Missing description for {0} - Please file a bug against Britney".format(verdict.name)

    def _render_dep_issues(self, dep_issues, invalid_deps):
        lastdep = ""
        res = []
        for x in sorted(dep_issues, key=lambda x: x.split('/')[0]):
            dep = x.split('/')[0]
            if dep != lastdep:
                seen = {}
            lastdep = dep
            for deptype in sorted(dep_issues[x], key=lambda y: str(y)):
                field = deptype
                if deptype in seen:
                    continue
                seen[deptype] = True
                if x in invalid_deps:
                    res.append("<li>%s: %s <a href=\"#%s\">%s</a> (not considered)\n" % (field, self.name, dep, dep))
                else:
                    res.append("<li>%s: %s <a href=\"#%s\">%s</a>\n" % (field, self.name, dep, dep))

        return "".join(res)

    def html(self):
        """Render the excuse in HTML"""
        res = "<a id=\"%s\" name=\"%s\">%s</a> (%s to %s)\n<ul>\n" % \
            (self.name, self.name, self.name, self.ver[0], self.ver[1])
        res += "<li>Migration status: %s\n" % self._format_verdict_summary()
        if self.maint:
            res = res + "<li>Maintainer: %s\n" % (self.maint)
        if self.section and self.section.find("/") > -1:
            res = res + "<li>Section: %s\n" % (self.section)
        if self.daysold is not None:
            if self.mindays == 0:
                res = res + ("<li>%d days old\n" % self.daysold)
            elif self.daysold < self.mindays:
                res = res + ("<li>Too young, only %d of %d days old\n" %
                             (self.daysold, self.mindays))
            else:
                res = res + ("<li>%d days old (needed %d days)\n" %
                             (self.daysold, self.mindays))
        for x in self.htmlline:
            res = res + "<li>" + x + "\n"
        res += self._render_dep_issues(self.all_deps, self.all_invalid_deps)

        for (n, a) in self.break_deps:
            if n not in self.all_deps:
                res += "<li>Ignoring %s depends: <a href=\"#%s\">%s</a>\n" % (a, n, n)

        res = res + "</ul>\n"
        return res

    def setbugs(self, oldbugs, newbugs):
        """"Set the list of old and new bugs"""
        self.newbugs.update(newbugs)
        self.oldbugs.update(oldbugs)

    def addreason(self, reason):
        """"adding reason"""
        self.reason[reason] = 1

    # TODO: remove
    def _text(self):
        """Render the excuse in text"""
        res = []
        for x in self.htmlline:
            res.append("" + x + "")
        return res

    def excusedata(self):
        """Render the excuse in as key-value data"""
        source = self.name
        if '_' in source:
            source = source.split("_")[0]
        if '/' in source:
            source = source.split("/")[0]
        if source[0] == '-':
            source = source[1:]
        excusedata = {}
        excusedata["excuses"] = self._text()
        excusedata["item-name"] = self.name
        excusedata["source"] = source
        excusedata["migration-policy-verdict"] = self._policy_verdict.name
        excusedata["old-version"] = self.ver[0]
        excusedata["new-version"] = self.ver[1]
        if self.maint:
            excusedata['maintainer'] = self.maint
        if self.section and self.section.find("/") > -1:
            excusedata['component'] = self.section.split('/')[0]
        if self.policy_info:
            excusedata['policy_info'] = self.policy_info
        if self.missing_builds or self.missing_builds_ood_arch:
            excusedata['missing-builds'] = {
                'on-architectures': sorted(self.missing_builds),
                'on-unimportant-architectures': sorted(self.missing_builds_ood_arch),
            }
        if self.all_invalid_deps:
            excusedata['invalidated-by-other-package'] = True
        if self.all_deps or self.all_invalid_deps \
                or self.break_deps or self.unsat_deps:
            excusedata['dependencies'] = dep_data = {}
            migrate_after = sorted(self.all_deps.keys() - self.all_invalid_deps)
            break_deps = [x for x, _ in self.break_deps if x not in self.all_deps]

            if self.all_invalid_deps:
                dep_data['blocked-by'] = sorted(self.all_invalid_deps)
            if migrate_after:
                dep_data['migrate-after'] = migrate_after
            if break_deps:
                dep_data['unimportant-dependencies'] = sorted(break_deps)
            if self.unsat_deps:
                dep_data['unsatisfiable-dependencies'] = {x: sorted(self.unsat_deps[x]) for x in self.unsat_deps}
        if self.needs_approval:
            status = 'not-approved'
            if any(h.type == 'unblock' for h in self.hints):
                status = 'approved'
            excusedata['manual-approval-status'] = status
        if self.hints:
            hint_info = [{
                             'hint-type': h.type,
                             'hint-from': h.user,
                         } for h in self.hints]

            excusedata['hints'] = hint_info
        if self.old_binaries:
            excusedata['old-binaries'] = {x: sorted(self.old_binaries[x]) for x in self.old_binaries}
        if self.forced:
            excusedata["forced-reason"] = sorted(list(self.reason.keys()))
            excusedata["reason"] = []
        else:
            excusedata["reason"] = sorted(list(self.reason.keys()))
        excusedata["is-candidate"] = self.is_valid
        return excusedata

    def add_bounty(self, policy, bounty):
        """"adding bounty"""
        self.bounty[policy] = bounty

    def add_penalty(self, policy, penalty):
        """"adding penalty"""
        self.penalty[policy] = penalty
