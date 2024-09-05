import discord
from contextlib import ExitStack
import STPyV8
import re
import pickle
from pathlib import Path
import requests
import google.generativeai as genai

CBOT_DEBUG = False
MAX_NUM_CONTEXTS = 16
URL_ALLOW_LIST = ["https://qrng.anu.edu.au/API/jsonl.php", "api.duckduckgo.com"]
MENTION_REGEX = r"<@(\d+)>"


def dprint(s):
    if CBOT_DEBUG:
        print(s)

token = None
preamble = None
gemini_key = None


with open('token.txt') as handle:
    token = handle.read()

with open('preamble.js') as handle:
    preamble = handle.read()

with open('geminikey.txt') as handle:
    gemini_key = handle.read()


def serialize_JSObject(self):
    keys = self.keys()
    out = {}

    for k in keys:
        data = self[k]
        if type(data) == STPyV8.JSObject:
            data = serialize_JSObject(data)
        out[k] = data
    
    return out




def parse_js_call(s):
    # we need to preserve spaces in split
    regex = '"([^"]*)"'
    quoteds = re.findall(regex, s)
    nonsense = 'sssdssdssdsd56137824'
    tokens = re.sub(regex, nonsense, s).split()
    final = []
    count = 0
    for tok in tokens:
        if tok == nonsense:
            final.append('"' + quoteds[count] + '"')
            count += 1
        else:
            final.append(tok)

    func_name = final[0]
    res = None
    if len(final) == 1:
        res = func_name + "()"
    else:
        res = func_name + "(" + ", ".join(final[1:]) + ")"
        
    dprint(f"#Func: {res}")
    return res


class UserGateway(STPyV8.JSClass):
    def init_state(self, id, client):
        self.s = {}
        self.userid = str(id)
        self.new_exports = []
        self.new_macros = []
        
        try:
            with open(f"userstate/{str(id)}", "rb") as handle:
                self.s = pickle.load(handle)
                if type(self.s) != type({}):
                    dprint(f"corrupted state read for {id}, resetting")
                    self.s = {}
        except Exception as e:
            dprint(str(e))
            self.s = {}
    
    def req(self, url):
        allowed = False
        for u in URL_ALLOW_LIST:
            if u in url:
                allowed = True
                break
        if allowed:
            response = requests.get(url)
            return response.text
        else:
            return None
    
    def gen(self, prompt, max_tokens):
        model = genai.GenerativeModel('models/gemini-1.5-flash')
        config = genai.GenerationConfig(max_output_tokens=max_tokens)
        response = model.generate_content(prompt, generation_config=config)
        return response
    

def get_js_context(client, id):
    # if there is already an assigned VM, return that
    if id in client.context_map:
        dprint(f"VM found for id {id}")
        return True, client.context_map[id]

    # otherwise, are we at limit?
    elif client.num_allocated_contexts == MAX_NUM_CONTEXTS:
        dprint(f"VM limit reached! Can't assign one to {id}")
        return False, None

    # otherwise, allocate
    else:
        gate = UserGateway()
        gate.init_state(id, client)
        ctx = STPyV8.JSContext(gate)
        client.context_map[id] = ctx
        exec_js_with_context(ctx, id, client, preamble)
        client.num_allocated_contexts += 1
        dprint(f"Allocated new VM to {id}")
        return True, ctx


def save_state(ctx, id):
    state = ctx.eval("this.s")
    # convert to dicts one level down
    out_state = serialize_JSObject(state)

    dprint(f"Saving for {id} state: {out_state}")
    with open(f"userstate/{str(id)}", "wb") as handle:
        pickle.dump(out_state, handle)
    
def get_macros_and_exports(ctx, id, client):
    new_macros = ctx.eval("new_macros")
    dprint(new_macros)
    ctx.eval("reset_macros()")
    new_exports = ctx.eval("new_exports")
    dprint(new_exports)
    ctx.eval("reset_exports()")

    for name, var, text in new_macros:
        client.macro_map[id][name] = var, text
        dprint(f"Added to {id} macro : {name, var, text}")

    for export in new_exports:
        client.exports[id].append(export)
        dprint(f"Added to {id} export : {export}")

def run_js(ctx, code_str):
    res = ctx.eval(code_str)
    if type(res) == STPyV8.JSObject:
        res = serialize_JSObject(res)
    res = str(res)
    log = "\n".join(list(ctx.eval("stdout")))
    if res == "None":
        res = ''
    if log != '':
        res += " `" + log + "`"
    ctx.eval("reset_stdout()")
    return res

def handle_export_call(client, mention, body):
    mention = mention[2:][:-1]
    id = int(mention)
    exports = client.exports[id]

    found_ctx, ctx = get_js_context(client, id)
    if not found_ctx:
        raise Exception("Could not alloc VM for export call")
    
    else:
        export_func = body.split(maxsplit=1)[0]
        if export_func in exports:
            dprint(f"Invoking legal export func {export_func} as id {id}")
            code = parse_js_call(body)
            return exec_js_with_context(ctx, id, client, code)
        else:
            raise Exception(f"Illegal export invocation: {export_func} as {id}")

def exec_js_with_context(ctx, id, client, code):
    with ctx as ctx:
        reply = run_js(ctx, code)
        get_macros_and_exports(ctx, id, client)
        save_state(ctx, id)
        return reply

class CampaignBotClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        for guild in client.guilds:
            if guild.name == "Noobs and Dragons":
                client.member_map = {}
                async for member in guild.fetch_members():
                    client.member_map[member.id] = member
                    client.macro_map[member.id] = {}
                    client.exports[member.id] = []
                    dprint(member.name)

    async def on_message(self, message):
        # prevent bot loop
        if message.author == client.user or message.author.bot:
            return

        text = message.content
        dprint(f"Recv: {text}")
        text = text.strip()
        cmd = text[1:].strip()
        id = message.author.id

        if len(text) < 2:
            dprint("Message too small")
            return

        # push this up so that macros in the preamble are still registered
        found_ctx, ctx = get_js_context(client, message.author.id)
        
        # first evaluate macros
        macros = client.macro_map[id]
        try:
            if text[0] == "#":
                macro_name, macro_var_text = cmd.split(maxsplit=1)
                if macro_name in macros:
                    macro_var, macro_text = macros[macro_name]
                    text = macro_text.replace(macro_var, macro_var_text)
                    dprint(f"After macro eval: {text}")

        except Exception as e:
            dprint(f"Macro check error: {e}")

        is_cbot_eval = text[0] == '$'
        is_cbot_quickeval = text[0] == '#'
        is_cbot_edit = text[0] == '&'

        is_cbot_command = is_cbot_eval or is_cbot_quickeval or is_cbot_edit
        
        if not is_cbot_command:
            return
        
        dprint(f"Is a cbot command {text[0]}")
        
        cmd = text[1:]
        
        if not found_ctx:
            await message.channel.send(f"{message.author.mention} VM limit reached, rip bozo")
            return
        
        try:
            reply = None


            if is_cbot_eval:
                code = cmd
                reply = exec_js_with_context(ctx, id, client, code)

            elif is_cbot_quickeval:
                code = cmd
                # might be an export, need to get the right context then
                sp = cmd.split(maxsplit=1)
                is_export_call = False
                if len(sp) >= 2:
                    match = re.search(MENTION_REGEX, sp[0])
                    if match:
                        is_export_call = True
                        dprint(f"Export call found: {cmd}")
                
                if is_export_call:
                    reply = handle_export_call(client, sp[0], sp[1])
                else:    
                    code = parse_js_call(cmd)
                    reply = exec_js_with_context(ctx, id, client, code)
                
            else:
                edit_cmd = cmd[0]
                cmd_s = cmd[1:].strip()
                edit_strs = cmd_s.split(maxsplit=1)
                dprint(edit_strs)
                filename = edit_strs[0]
                
                if edit_cmd == '+':
                    if len(edit_strs) != 2:
                        raise Exception("Malformed write, should be &+filename code")
                    
                    write_contents = edit_strs[1]
                    with open(f"usercode/{filename}", "w") as handle:
                        handle.write(write_contents)
                        
                elif edit_cmd == "&":
                    with open(f"usercode/{filename}") as handle:
                        code = handle.read()
                        reply = exec_js_with_context(ctx, id, client, code)

                elif edit_cmd == "*":
                    with open(f"usercode/{filename}") as handle:
                        reply = handle.read()
                
                else:
                    raise Exception("Unknown edit command")        
            
            if reply != None and reply != "" and reply != "None":
                await message.channel.send(str(message.author.mention) + " " + str(reply))
            else:
                await message.add_reaction("✅")

        except FileNotFoundError as e:
            await message.add_reaction("❌")
            await message.add_reaction("📄")
        except Exception as e:
            await message.channel.send(str(message.author.mention) + " " + str(e))
        

genai.configure(api_key=gemini_key)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = CampaignBotClient(intents=intents)
client.num_allocated_contexts = 0
client.context_map = {}
# client.isolate_map = {}
client.member_map = {}
client.macro_map = {}
client.exports = {}
client.run(token)
