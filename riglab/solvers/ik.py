# This file is part of riglab.
# Copyright (C) 2014  Cesar Saez

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation version 3.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from wishlib.si import si, C

from .base import Base
from ..manipulator import Manipulator
from .. import utils


class IK(Base):

    def custom_inputs(self):
        super(IK, self).custom_inputs()
        # add squash and stretch parameters
        param = self.input.get("parameters")
        if not self.input.get("stretch"):
            self.input["stretch"] = param.AddParameter3("stretch", C.siBool, 1)
        if not self.input.get("squash"):
            self.input["squash"] = param.AddParameter3("squash", C.siBool, 0)
        self.input.get("squash").Value = len(self.input["skeleton"]) == 2

    def custom_anim(self):
        # create
        anim_root = Manipulator.new(parent=self.input.get("root"))
        anim_root.owner = {"obj": self.obj, "class": self.classname}
        anim_root.icon.shape = self.shape_color.get("ikIcon")
        anim_root.icon.color = self.shape_color.get(self.side)[0]
        anim_eff, anim_upv = anim_root.duplicate(2)  # OPTIMIZATION
        # anim_eff.icon.connect = anim_root.anim
        anim_upv.icon.shape = self.shape_color.get("upIcon")
        anim_upv.icon.color = self.shape_color.get(self.side)[1]
        anim_upv.icon.size = 0.25
        anim_upv.icon.connect = self.input.get("skeleton")[0]
        for i, ctrl in enumerate((anim_root, anim_upv, anim_eff)):
            ctrl.rename(self.name, i, side=self.side)
            self.helper.get("hidden").extend(
                [ctrl.orient, ctrl.zero, ctrl.space])
        # align
        sk = self.input.get("skeleton")
        data = utils.curve_data(self.helper["curve"])
        if len(sk) > 2:
            anim_root.align_matrix4(data[0][0])
            anim_eff.align_matrix4(data[0][-1])
        else:
            anim_root.align(sk[0])
            anim_eff.align(sk[-1])
        anim_upv.align(anim_root.anim)
        si.Translate(anim_upv.zero, 0, -data[1][0], 0, "siRelative", "siLocal")
        # save attributes
        self.input["anim"] = (anim_root.anim, anim_upv.anim, anim_eff.anim)

    def custom_build(self):
        super(IK, self).custom_build()
        # setup
        root = self._ikchain()
        # connect ikchain
        root.Kinematics.AddConstraint("Position", self.input["anim"][0])
        root.Effector.Kinematics.AddConstraint(
            "Position", self.input["anim"][-1])
        for i, bone in enumerate(root.Bones):
            self.output.get("tm")[i].Kinematics.AddConstraint("Pose", bone)
        first_bone = root.Bones(0)
        # backup global transforms
        m4 = first_bone.Kinematics.Global.Transform.Matrix4.Get2()
        args = (first_bone.FullName, self.input["anim"][1].FullName)
        si.ApplyOp("SkeletonUpVector", "{0};{1}".format(*args))
        # compare to define roll value
        angle = 0
        while not self.equal(first_bone.Kinematics.Global.Transform.Matrix4.Get2(), m4):
            angle += 90
            first_bone.Properties(
                "Kinematic Joint").Parameters("roll").Value = angle
            if angle > 360:
                break
        # stretching parameters
        if not self.helper.get("ss_factor"):
            if not self.helper.get("parameters"):
                p = self.helper["root"].AddCustomProperty("Helper_Parameters")
                self.helper["parameters"] = p
            ss_factor = p.AddParameter3("ss_factor", C.siFloat, 1, 0, 999)
            self.helper["ss_factor"] = ss_factor
        # ss_factor expression
        kwds = {"root": self.input["anim"][0].FullName,
                "eff": self.input["anim"][-1].FullName,
                "total_length": sum(utils.curve_data(self.helper["curve"])[1])}
        expr = "ctr_dist({root}., {eff}.) / {total_length}".format(**kwds)
        self.helper["ss_factor"].AddExpression(expr)
        # calc expr for each bone
        kwds = {"ss_factor": self.helper.get("ss_factor"),
                "stretch": self.input.get("stretch").FullName,
                "squash": self.input.get("squash").FullName}
        expr = "COND({stretch} * {squash}, {ss_factor}, COND({stretch} == 1, MAX({ss_factor}, 1), COND({squash} == 1, MIN({ss_factor}, 1), 1)))"
        expr = expr.format(**kwds)
        first_bone.Kinematics.Local.Parameters("sclx").AddExpression(expr)
        # set snap reference
        self.get_manipulator(self.input["anim"][0].FullName).snap_ref(
            self.input["skeleton"][0])
        self.get_manipulator(self.input["anim"][1].FullName).snap_ref(
            self.input["skeleton"][0])
        self.get_manipulator(self.input["anim"][2].FullName).snap_ref(
            self.input["skeleton"][-1])

    def _ikchain(self):
        root = utils.curve2chain(self.helper.get("curve"),
                                 parent=self.helper["root"])
        # rename
        root.Name = self.nm.qn(self.name + "Root", "jnt", side=self.side)
        root.Effector.Name = self.nm.qn(
            self.name + "Eff", "jnt", side=self.side)
        for i in range(root.Bones.Count):
            root.Bones(i).Name = self.nm.qn(
                self.name, "jnt", i, side=self.side)
        # cleanup
        self.helper.get("hidden").extend(list(root.Bones))
        self.helper.get("hidden").extend([root, root.Effector])
        return root

    @staticmethod
    def validate(skeleton):
        return len(skeleton) >= 2

    @staticmethod
    def equal(t1, t2):
        for i, _ in enumerate(t1):
            if int(abs(t1[i] - t2[i]) * 1000) > 0:
                return False
        return True
