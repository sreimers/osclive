import time
import math
from pythonosc import dispatcher
from pythonosc import udp_client
from pythonosc import osc_packet
from pythonosc import osc_message_builder

from config import *

aux_sel         = ["aux1", "aux2", "aux3", "aux4", "fxa", "fxb"]
channel_sel     = ["ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "ch9", "ch10", "ch11", "ch12", "main"]
channel_ctrls   = ["gain","pan",
        "eqlow", "eqmid", "eqhigh", "eqlowshelf", "eqmidhiq", "eqhighshelf", "eqlowfreq", "eqlowgain", "eqmidfreq", "eqmidgain", "eqhighfreq", "eqhighgain",
        "hpf", "hpffreq", "gate", "gatethresh", "comp", "compauto", "compthresh", "compresponse", "compgain", "compratio"]

CLIENT_CHANNELS = 12

def float2db(val):
    ret = (36.1*math.log(val*100+0.1) - 156.25)
    if (ret < -100):
        return "-oo dB"
    else:
        return "%.1f dB" % ret
def float2eqlow(val):
    return (69.6*math.log(val+0.001) + 333)
def float2eqmid(val):
    return (524*math.log(val+0.001) + 2500)
def float2eqhigh(val):
    return (2690*math.log(val+0.001) + 12885)


def osc_create_msg(addr, value):
    msg = osc_message_builder.OscMessageBuilder(address = addr)
    msg.add_arg(value)
    msg = msg.build()
    return msg

class OSCClient(udp_client.UDPClient):
    def __init__(self, ip, port, server):
        udp_client.UDPClient.__init__(self, ip, port)

        self.dispatcher = dispatcher.Dispatcher()
        self.server = server
        self.server.add_update_callback(self.sl_control_handler)
        self.server.level_callbacks.append(self.sl_level_handler)

        self.selaux = "aux1"
        self.selch = "ch1"

        self.dispatcher.set_default_handler(print)
        self.dispatcher.map("/accxyz", lambda u,w,x,y,z:None, 0)
        self.dispatcher.map("/ping", lambda u,w:None, 0)

        self.init_dispatcher()
        self.init()

    def handle_request(self, request):
        try:
            packet = osc_packet.OscPacket(request[0])
            for timed_msg in packet.messages:
                now = time.time()
                handlers = self.dispatcher.handlers_for_address(timed_msg.message.address)
                if not handlers:
                    continue
                # If the message is to be handled later, then so be it.
                if timed_msg.time > now:
                    time.sleep(timed_msg.time - now)
                for handler in handlers:
                    if handler.args:
                        handler.callback(timed_msg.message.address, handler.args, *timed_msg.message)
                    else:
                        handler.callback(timed_msg.message.address, *timed_msg.message)
        except osc_packet.ParseError:
            pass

    def osc_send_control(self, addr, value):
        #print("Sending %s = %s" % (addr, value))
        msg = osc_create_msg(addr, value)
        self.send(msg)

    def init_dispatcher(self):
        # PAGE "Main"
        for channel in channel_sel:
            self.dispatcher.map("/%s/gain" % channel, self.main_handler, channel)

        # PAGE "Aux"
        for i in aux_sel:
            self.dispatcher.map("/aux/sel/%s" % i, self.aux_select_handler, i)

        for i in range(1, CLIENT_CHANNELS+1):
            self.dispatcher.map("/aux/ch%d"%i, self.aux_volume_handler, "ch%d" % i)
        self.dispatcher.map("/aux/main", self.aux_main_volume_handler)

        # PAGE "Channel"
        for i in channel_sel:
            self.dispatcher.map("/channel/sel/%s" % i, self.channel_select_handler, "%s" % i, i)
        #self.dispatcher.map("/channel/sel/1/%d" % (CLIENT_CHANNELS+1), self.channel_select_handler, "main", 8)

        for control in self.server.CHANNEL_CTRL:
            self.dispatcher.map("/channel/%s" % control, self.channel_control_handler, control)
        self.dispatcher.map("/channel/panreset", self.channel_control_extra_handler, "panreset")

        # PAGE "Effect"

        # PAGE "Equaliser"

    def init(self):
		# PAGE "Main"
        for channel in channel_sel:
            for ctrl in ["gain"]:
                value = self.server.get_control(channel, ctrl)
                self.send(osc_create_msg("/%s/%s" % (channel, ctrl), value))

		# PAGE "Aux": Update
        self.aux_select_handler("/aux/sel/%s" % aux_sel[0], [aux_sel[0]], 1)

		# PAGE "Channel": Update
        self.channel_select_handler("/channel/sel/%s" % channel_sel[0], [channel_sel[0]], 1)

		# Update labels
        for ch, name in active_channels.items():
            self.send(osc_create_msg("/%s/label" % ch, name))
            self.send(osc_create_msg("/aux/%s_label" % ch, name))
        for ch, name in active_auxs.items():
            self.send(osc_create_msg("/aux/sel/%s_label" % ch, name))
        #for ch in channel_sel:
        #    if ch not in [i[0] for i in active_channels]:
        #        pass

    def sl_level_handler(self):
        for ch in range(1, CLIENT_CHANNELS+1):
            value = self.server.get_level("ch%d" % ch) / 32.0
            self.osc_send_control("/ch%d/level" % ch, value)
        self.osc_send_control("/main/level", self.server.get_level("main")/32.0)
        self.osc_send_control("/channel/level", self.server.get_level(self.selch)/32.0)

    def sl_control_handler(self, channel, ctrl, value):
        print("SL Control handler, channel %s, ctrl %s" %( channel, ctrl))
        
        # PAGE "Main"
        if(ctrl == "gain" and channel in ["ch%d"%ch for ch in range(1,CLIENT_CHANNELS+1)]) or \
          (ctrl == "gain" and channel == "main"):
            self.osc_send_control("/%s/%s" % (channel, ctrl), value)
            self.osc_send_control("/%s/gain_db" % channel, float2db(value))
            self.osc_send_control("/%s/%s" % (channel, ctrl), value)

        # PAGE "Aux"
        if(ctrl == self.selaux and channel in ["ch%d"%ch for ch in range(1,CLIENT_CHANNELS+1)]):
            self.osc_send_control("/aux/%s" % channel, value)
            self.osc_send_control("/aux/%s_gain_db" % channel, float2db(value))
        if(ctrl == "gain" and channel == self.selaux):
            self.osc_send_control("/aux/gain", value)
            self.osc_send_control("/aux/gain_db", float2db(value))

        # PAGE "Channel"
        if(self.selch == channel):
            if(ctrl in channel_ctrls):
                self.osc_send_control("/channel/%s" % ctrl, value)
                #if(ctrl == "eqlowgain"):
                #    self.osc_send_control("/%s/gain_db" % channel, "%.1f" % float2db(value))


        #for i in range(1, CLIENT_CHANNELS+1):
        #    val = self.server.get_control(channel_map["in%d"%i], self.selaux)
        #    self.send(osc_create_msg("/aux/gain%d" % i, val))

        # PAGE "Effect"
        # PAGE "Equaliser"

    def aux_select_handler(self, addr, args, value):
        self.selaux = args[0]

        #for i in range(1,len(aux_sel)+1):
        #    self.send(osc_create_msg("/aux/sel/1/%i" % i, 0))
        #self.send(osc_create_msg("/aux/sel/1/%i" % index, 1))
        for i in active_auxs:
            self.send(osc_create_msg("/aux/sel/%s_label" % i, "%s" % active_auxs[i]))
            self.send(osc_create_msg("/aux/sel/%s_label/color" % i, "gray"))
            self.send(osc_create_msg("/aux/sel/%s/color" % i, "gray"))
        self.send(osc_create_msg("/aux/sel/%s_label" % self.selaux, "--> %s <--" % active_auxs[self.selaux]))
        self.send(osc_create_msg("/aux/sel/%s_label/color" % self.selaux, "yellow"))
        self.send(osc_create_msg("/aux/sel/%s/color" % self.selaux, "yellow"))
        
        for i in range(1, CLIENT_CHANNELS+1):
            val = self.server.get_control("ch%d" % i, self.selaux)
            self.send(osc_create_msg("/aux/ch%d" % i, val))

        val = self.server.get_control(self.selaux, "gain")
        self.send(osc_create_msg("/aux/main", val))

    def channel_select_handler(self, addr, args, value):
        self.selch = args[0]

        for i in active_channels:
            self.send(osc_create_msg("/channel/sel/%s_label" % i, "%s" % active_channels[i]))
            self.send(osc_create_msg("/channel/sel/%s_label/color" % i, "gray"))
            self.send(osc_create_msg("/channel/sel/%s/color" % i, "gray"))
        self.send(osc_create_msg("/channel/sel/%s_label" % self.selch, "--> %s <--" % active_channels[self.selch]))
        self.send(osc_create_msg("/channel/sel/%s_label/color" % self.selch, "yellow"))
        self.send(osc_create_msg("/channel/sel/%s/color" % self.selch, "yellow"))
            
        for control in channel_ctrls:
            val = self.server.get_control(self.selch, control)
            self.send(osc_create_msg("/channel/%s" % control, val))

    def main_handler(self, addr, args, value):
        self.server.set_control(args[0], "gain", value)

    def aux_volume_handler(self, addr, args, value):
        self.server.set_control(args[0], self.selaux, value)

    def aux_main_volume_handler(self, addr, value):
        self.server.set_control(self.selaux, "gain", value)

    def channel_control_handler(self, addr, args, value):
        self.server.set_control(self.selch, args[0], value)

    def channel_control_extra_handler(self, addr, args, value):
        if (args[0] == "panreset"):
            self.server.set_control(self.selch, "pan", 0.5)
