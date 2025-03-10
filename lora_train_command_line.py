import gc
import time
from typing import Union
import os
import json

import torch.cuda
import train_network
import library.train_util as util
import argparse


class ArgStore:
    # Represents the entirety of all possible inputs for sd-scripts. they are ordered from most important to least
    def __init__(self):
        # Important, these are the most likely things you will modify
        self.base_model: str = r""  # example path, r"E:\sd\stable-diffusion-webui\models\Stable-diffusion\nai.ckpt"
        self.img_folder: str = r""  # is the folder path to your img folder, make sure to follow the guide
                                    # here for folder setup: https://rentry.org/2chAI_LoRA_Dreambooth_guide_english#for-kohyas-script
        self.output_folder: str = r""  # just the folder all epochs/safetensors are output
        self.change_output_name: Union[str, None] = None  # changes the output name of the epochs
        self.save_json_folder: Union[str, None] = None  # OPTIONAL, saves a json folder of your config to whatever location you set here.
        self.load_json_path: Union[str, None] = None  # OPTIONAL, loads a json file partially changes the config to match.
        self.json_load_skip_list: Union[list[str], None] = None  # OPTIONAL, allows the user to define what they skip when loading a json,
                                                                 # IMPORTANT: by default it loads everything, including all paths,
                                                                 # format to exclude things is like so: ["base_model", "img_folder", "output_folder"]
        self.multi_run_folder: Union[str, None] = None  # OPTIONAL, set to a folder with jsons generated by my script and it will begin training using those scripts.
                                                        # keep in mind, it will ignore the json_load_skip_list to ensure that everything gets loaded.
                                                        # IMPORTANT: This will also ignore all params set here and instead use all params in the json files.
        self.save_json_only: bool = False  # set to true if you don't want to do any training, but rather just want to generate a json
        self.caption_dropout_rate: Union[float, None] = None  # The rate at which captions for files get dropped.
        self.caption_dropout_every_n_epochs: Union[int, None] = None  # Defines how often an epoch will completely ignore
                                                                      # captions, EX. 3 means it will ignore captions at epochs 3, 6, and 9
        self.caption_tag_dropout_rate: Union[float, None] = None  # Defines the rate at which a tag would be dropped, rather than the entire caption file

        self.net_dim: int = 128  # network dimension, 128 is the most common, however you might be able to get lesser to work
        self.alpha: float = 64  # represents the scalar for training. the lower the alpha,
                                # the less gets learned per step. if you want the older way of training, set this to dim
        # list of schedulers: linear, cosine, cosine_with_restarts, polynomial, constant, constant_with_warmup
        self.scheduler: str = "cosine_with_restarts"  # the scheduler for learning rate. Each does something specific
        self.cosine_restarts: Union[int, None] = 1  # OPTIONAL, represents the number of times it restarts. Only matters if you are using cosine_with_restarts
        self.scheduler_power: Union[float, None] = 1  # OPTIONAL, represents the power of the polynomial. Only matters if you are using polynomial
        self.warmup_lr_ratio: Union[float, None] = None  # OPTIONAL, Calculates the number of warmup steps based on the
                                                         # ratio given. Make sure to set this if you are using
                                                         # constant_with_warmup, None to ignore
        self.learning_rate: Union[float, None] = 1e-4  # OPTIONAL, when not set, lr gets set to 1e-3 as per adamW. Personally, I suggest actually setting this as lower lr seems to be a small bit better.
        self.text_encoder_lr: Union[float, None] = None  # OPTIONAL, Sets a specific lr for the text encoder, this overwrites the base lr I believe, None to ignore
        self.unet_lr: Union[float, None] = None  # OPTIONAL, Sets a specific lr for the unet, this overwrites the base lr I believe, None to ignore
        self.num_workers: int = 1  # The number of threads that are being used to load images, lower speeds up
                                   # the start of epochs, but slows down the loading of data. The assumption here is
                                   # that it increases the training time as you reduce this value
        self.persistent_workers: bool = True  # makes workers persistent, further reduces/eliminates the lag in between epochs. however it may increase memory usage

        self.batch_size: int = 1  # The number of images that get processed at one time, this is directly proportional
                                  # to your vram and resolution. with 12gb of vram, at 512 reso, you can get a maximum of 6 batch size
        self.num_epochs: int = 1  # The number of epochs, if you set max steps this value is ignored as it doesn't calculate steps.
        self.save_every_n_epochs: Union[int, None] = 1  # OPTIONAL, how often to save epochs, None to ignore
        self.shuffle_captions: bool = False  # OPTIONAL, False to ignore
        self.keep_tokens: Union[int, None] = None  # OPTIONAL, None to ignore
        self.max_steps: Union[int, None] = None  # OPTIONAL, if you have specific steps you want to hit, this allows you to set it directly. None to ignore
        self.tag_occurrence_txt_file: bool = False  # OPTIONAL, creates a txt file that has the entire occurrence of all tags in your dataset
                                                    # the metadata will also have this so long as you have metadata on, so no reason to have this on by default
                                                    # will automatically output to the same folder as your output checkpoints

        # These are the second most likely things you will modify
        self.train_resolution: int = 512
        self.min_bucket_resolution: int = 320
        self.max_bucket_resolution: int = 960
        self.lora_model_for_resume: Union[str, None] = None  # OPTIONAL, takes an input lora to continue training from,
                                                             # not exactly the way it *should* be, but it works, None to ignore
        self.save_state: bool = False  # OPTIONAL, is the intended way to save a training state to use for continuing training, False to ignore
        self.load_previous_save_state: Union[str, None] = None  # OPTIONAL, is the intended way to load a training state to use for continuing training, None to ignore
        self.training_comment: Union[str, None] = None  # OPTIONAL, great way to put in things like activation tokens right
                                                        # into the metadata. seems to not work at this point and time
        self.unet_only: bool = False  # OPTIONAL, set it to only train the unet
        self.text_only: bool = False  # OPTIONAL, set it to only train the text encoder

        # These are the least likely things you will modify
        self.reg_img_folder: Union[str, None] = None  # OPTIONAL, None to ignore
        self.clip_skip: int = 2  # If you are training on a model that is anime based, keep this at 2 as most models are designed for that
        self.test_seed: int = 23  # this is the "reproducable seed", basically if you set the seed to this,
                                  # you should be able to input a prompt from one of your training images and get a close representation of it
        self.prior_loss_weight: float = 1  # is the loss weight much like Dreambooth, is required for LoRA training
        self.gradient_checkpointing: bool = False  # OPTIONAL, enables gradient checkpointing
        self.gradient_acc_steps: Union[int, None] = None  # OPTIONAL, not sure exactly what this means
        self.mixed_precision: str = "fp16"  # If you have the ability to use bf16, do it, it's better
        self.save_precision: str = "fp16"  # You can also save in bf16, but because it's not universally supported, I suggest you keep saving at fp16
        self.save_as: str = "safetensors"  # list is pt, ckpt, safetensors
        self.caption_extension: str = ".txt"  # the other option is .captions, but since wd1.4 tagger outputs as txt files, this is the default
        self.max_clip_token_length = 150  # can be 75, 150, or 225 I believe, there is no reason to go higher than 150 though
        self.buckets: bool = True
        self.xformers: bool = True
        self.use_8bit_adam: bool = True
        self.cache_latents: bool = True
        self.color_aug: bool = False  # IMPORTANT: Clashes with cache_latents, only have one of the two on!
        self.flip_aug: bool = False
        self.random_crop: bool = False  # IMPORTANT: Clashes with cache_latents
        self.vae: Union[str, None] = None  # Seems to only make results worse when not using that specific vae, should probably not use
        self.no_meta: bool = False  # This removes the metadata that now gets saved into safetensors, (you should keep this on)
        self.log_dir: Union[str, None] = None  # output of logs, not useful to most people.
        self.bucket_reso_steps: Union[int, None] = None  # is the steps that is taken when making buckets, can be any
                                                         # can be any positive value from 1 up
        self.bucket_no_upscale: bool = False  # Disables up-scaling for images in buckets
        self.v2: bool = False  # Sets up training for SD2.1
        self.v_parameterization: bool = False  # Only is used when v2 is also set and you are using the 768x version of v2

    # Creates the dict that is used for the rest of the code, to facilitate easier json saving and loading
    @staticmethod
    def convert_args_to_dict():
        return ArgStore().__dict__


def main():
    parser = argparse.ArgumentParser()
    setup_args(parser)
    pre_args = parser.parse_args()
    multi_path = ArgStore.convert_args_to_dict()['multi_run_folder']
    if multi_path or pre_args.multi_run_path:
        multi_path = multi_path if multi_path else pre_args.multi_run_path
        if multi_path and not ensure_path(multi_path, "multi_path"):
            raise FileNotFoundError("Failed to find the path to where every json file is")
        for file in os.listdir(multi_path):
            if os.path.isdir(file) or file.split(".")[-1] != "json":
                continue
            arg_dict = ArgStore.convert_args_to_dict()
            arg_dict["json_load_skip_list"] = None
            load_json(os.path.join(multi_path, file), arg_dict)
            args = create_arg_space(arg_dict)
            args = parser.parse_args(args)
            if arg_dict['tag_occurrence_txt_file']:
                get_occurrence_of_tags(arg_dict)
            train_network.train(args)
            gc.collect()
            torch.cuda.empty_cache()
            if not os.path.exists(os.path.join(multi_path, "complete")):
                os.makedirs(os.path.join(multi_path, "complete"))
            os.rename(os.path.join(multi_path, file), os.path.join(multi_path, "complete", file))
        quit(0)
    arg_dict = ArgStore.convert_args_to_dict()
    if (pre_args.load_json_path or arg_dict["load_json_path"]) and not arg_dict["save_json_only"]:
        load_json(pre_args.load_json_path if pre_args.load_json_path else arg_dict['load_json_path'], arg_dict)
    if pre_args.save_json_path or arg_dict["save_json_folder"]:
        save_json(pre_args.save_json_path if pre_args.save_json_path else arg_dict['save_json_folder'], arg_dict)
    args = create_arg_space(arg_dict)
    args = parser.parse_args(args)
    if arg_dict['tag_occurrence_txt_file']:
        get_occurrence_of_tags(arg_dict)
    if not arg_dict["save_json_only"]:
        train_network.train(args)


def create_arg_space(args: dict) -> [str]:
    if not ensure_path(args["base_model"], "base_model", {"ckpt", "safetensors"}):
        raise FileNotFoundError("Failed to find base model, make sure you have the correct path")
    if not ensure_path(args["img_folder"], "img_folder"):
        raise FileNotFoundError("Failed to find the image folder, make sure you have the correct path")
    if not ensure_path(args["output_folder"], "output_folder"):
        raise FileNotFoundError("Failed to find the output folder, make sure you have the correct path")
    # This is the list of args that are to be used regardless of setup
    output = ["--network_module=networks.lora", f"--pretrained_model_name_or_path={args['base_model']}",
              f"--train_data_dir={args['img_folder']}", f"--output_dir={args['output_folder']}",
              f"--prior_loss_weight={args['prior_loss_weight']}", f"--caption_extension=" + args['caption_extension'],
              f"--resolution={args['train_resolution']}", f"--train_batch_size={args['batch_size']}",
              f"--mixed_precision={args['mixed_precision']}", f"--save_precision={args['save_precision']}",
              f"--network_dim={args['net_dim']}", f"--save_model_as={args['save_as']}",
              f"--clip_skip={args['clip_skip']}", f"--seed={args['test_seed']}",
              f"--max_token_length={args['max_clip_token_length']}", f"--lr_scheduler={args['scheduler']}",
              f"--network_alpha={args['alpha']}", f"--max_data_loader_n_workers={args['num_workers']}"]
    if not args['max_steps']:
        output.append(f"--max_train_epochs={args['num_epochs']}")
        output += create_optional_args(args, find_max_steps(args))
    else:
        output.append(f"--max_train_steps={args['max_steps']}")
        output += create_optional_args(args, args['max_steps'])
    return output


def create_optional_args(args: dict, steps):
    output = []
    if args["reg_img_folder"]:
        if not ensure_path(args["reg_img_folder"], "reg_img_folder"):
            raise FileNotFoundError("Failed to find the reg image folder, make sure you have the correct path")
        output.append(f"--reg_data_dir={args['reg_img_folder']}")

    if args['lora_model_for_resume']:
        if not ensure_path(args['lora_model_for_resume'], "lora_model_for_resume", {"pt", "ckpt", "safetensors"}):
            raise FileNotFoundError("Failed to find the lora model, make sure you have the correct path")
        output.append(f"--network_weights={args['lora_model_for_resume']}")

    if args['save_every_n_epochs']:
        output.append(f"--save_every_n_epochs={args['save_every_n_epochs']}")
    else:
        output.append("--save_every_n_epochs=999999")

    if args['shuffle_captions']:
        output.append("--shuffle_caption")

    if args['keep_tokens'] and args['keep_tokens'] > 0:
        output.append(f"--keep_tokens={args['keep_tokens']}")

    if args['buckets']:
        output.append("--enable_bucket")
        output.append(f"--min_bucket_reso={args['min_bucket_resolution']}")
        output.append(f"--max_bucket_reso={args['max_bucket_resolution']}")

    if args['use_8bit_adam']:
        output.append("--use_8bit_adam")

    if args['xformers']:
        output.append("--xformers")

    if args['color_aug']:
        if args['cache_latents']:
            print("color_aug and cache_latents conflict with one another. Please select only one")
            quit(1)
        output.append("--color_aug")

    if args['flip_aug']:
        output.append("--flip_aug")

    if args['cache_latents']:
        output.append("--cache_latents")

    if args['warmup_lr_ratio'] and args['warmup_lr_ratio'] > 0:
        warmup_steps = int(steps * args['warmup_lr_ratio'])
        output.append(f"--lr_warmup_steps={warmup_steps}")

    if args['gradient_checkpointing']:
        output.append("--gradient_checkpointing")

    if args['gradient_acc_steps'] and args['gradient_acc_steps'] > 0 and args['gradient_checkpointing']:
        output.append(f"--gradient_accumulation_steps={args['gradient_acc_steps']}")

    if args['learning_rate'] and args['learning_rate'] > 0:
        output.append(f"--learning_rate={args['learning_rate']}")

    if args['text_encoder_lr'] and args['text_encoder_lr'] > 0:
        output.append(f"--text_encoder_lr={args['text_encoder_lr']}")

    if args['unet_lr'] and args['unet_lr'] > 0:
        output.append(f"--unet_lr={args['unet_lr']}")

    if args['vae']:
        output.append(f"--vae={args['vae']}")

    if args['no_meta']:
        output.append("--no_metadata")

    if args['save_state']:
        output.append("--save_state")

    if args['load_previous_save_state']:
        if not ensure_path(args['load_previous_save_state'], "previous_state"):
            raise FileNotFoundError("Failed to find the save state folder, make sure you have the correct path")
        output.append(f"--resume={args['load_previous_save_state']}")

    if args['change_output_name']:
        output.append(f"--output_name={args['change_output_name']}")

    if args['training_comment']:
        output.append(f"--training_comment={args['training_comment']}")

    if args['cosine_restarts'] and args['scheduler'] == "cosine_with_restarts":
        output.append(f"--lr_scheduler_num_cycles={args['cosine_restarts']}")

    if args['scheduler_power'] and args['scheduler'] == "polynomial":
        output.append(f"--lr_scheduler_power={args['scheduler_power']}")

    if args['persistent_workers']:
        output.append("--persistent_data_loader_workers")

    if args['unet_only']:
        output.append("--network_train_unet_only")

    if args['text_only'] and not args['unet_only']:
        output.append("--network_train_text_encoder_only")
    
    if args["log_dir"]:
        output.append(f"--logging_dir={args['log_dir']}")

    if args['bucket_reso_steps']:
        output.append(f"--bucket_reso_steps={args['bucket_reso_steps']}")

    if args['bucket_no_upscale']:
        output.append("--bucket_no_upscale")

    if args['random_crop'] and not args['cache_latents']:
        output.append("--random_crop")

    if args['caption_dropout_rate']:
        output.append(f"--caption_dropout_rate={args['caption_dropout_rate']}")

    if args['caption_dropout_every_n_epochs']:
        output.append(f"--caption_dropout_every_n_epochs={args['caption_dropout_every_n_epochs']}")

    if args['caption_tag_dropout_rate']:
        output.append(f"--caption_tag_dropout_rate={args['caption_tag_dropout_rate']}")

    if args['v2']:
        output.append("--v2")

    if args['v2'] and args['v_parameterization']:
        output.append("--v_parameterization")
    return output


def find_max_steps(args: dict) -> int:
    total_steps = 0
    folders = os.listdir(args["img_folder"])
    for folder in folders:
        if not os.path.isdir(os.path.join(args["img_folder"], folder)):
            continue
        num_repeats = folder.split("_")
        if len(num_repeats) < 2:
            print(f"folder {folder} is not in the correct format. Format is x_name. skipping")
            continue
        try:
            num_repeats = int(num_repeats[0])
        except ValueError:
            print(f"folder {folder} is not in the correct format. Format is x_name. skipping")
            continue
        imgs = 0
        for file in os.listdir(os.path.join(args["img_folder"], folder)):
            if os.path.isdir(file):
                continue
            ext = file.split(".")
            if ext[-1].lower() in {"png", "bmp", "gif", "jpeg", "jpg", "webp"}:
                imgs += 1
        total_steps += (num_repeats * imgs)
    total_steps = int((total_steps / args["batch_size"]) * args["num_epochs"])
    return total_steps


def add_misc_args(parser) -> None:
    parser.add_argument("--multi_run_path", type=str, default=None,
                        help="Path to load a set of json files to train all at once")
    parser.add_argument("--save_json_path", type=str, default=None,
                        help="Path to save a configuration json file to")
    parser.add_argument("--load_json_path", type=str, default=None,
                        help="Path to a json file to configure things from")
    parser.add_argument("--no_metadata", action='store_true',
                        help="do not save metadata in output model / メタデータを出力先モデルに保存しない")
    parser.add_argument("--save_model_as", type=str, default="safetensors", choices=[None, "ckpt", "pt", "safetensors"],
                        help="format to save the model (default is .safetensors) / モデル保存時の形式（デフォルトはsafetensors）")

    parser.add_argument("--unet_lr", type=float, default=None, help="learning rate for U-Net / U-Netの学習率")
    parser.add_argument("--text_encoder_lr", type=float, default=None,
                        help="learning rate for Text Encoder / Text Encoderの学習率")
    parser.add_argument("--lr_scheduler_num_cycles", type=int, default=1,
                        help="Number of restarts for cosine scheduler with restarts / cosine with restartsスケジューラでのリスタート回数")
    parser.add_argument("--lr_scheduler_power", type=float, default=1,
                        help="Polynomial power for polynomial scheduler / polynomialスケジューラでのpolynomial power")

    parser.add_argument("--network_weights", type=str, default=None,
                        help="pretrained weights for network / 学習するネットワークの初期重み")
    parser.add_argument("--network_module", type=str, default=None,
                        help='network module to train / 学習対象のネットワークのモジュール')
    parser.add_argument("--network_dim", type=int, default=None,
                        help='network dimensions (depends on each network) / モジュールの次元数（ネットワークにより定義は異なります）')
    parser.add_argument("--network_alpha", type=float, default=1,
                        help='alpha for LoRA weight scaling, default 1 (same as network_dim for same behavior as old version) / LoRaの重み調整のalpha値、デフォルト1（旧バージョンと同じ動作をするにはnetwork_dimと同じ値を指定）')
    parser.add_argument("--network_args", type=str, default=None, nargs='*',
                        help='additional argmuments for network (key=value) / ネットワークへの追加の引数')
    parser.add_argument("--network_train_unet_only", action="store_true",
                        help="only training U-Net part / U-Net関連部分のみ学習する")
    parser.add_argument("--network_train_text_encoder_only", action="store_true",
                        help="only training Text Encoder part / Text Encoder関連部分のみ学習する")
    parser.add_argument("--training_comment", type=str, default=None,
                        help="arbitrary comment string stored in metadata / メタデータに記録する任意のコメント文字列")


def setup_args(parser) -> None:
    util.add_sd_models_arguments(parser)
    util.add_dataset_arguments(parser, True, True, True)
    util.add_training_arguments(parser, True)
    add_misc_args(parser)


def ensure_path(path, name, ext_list=None) -> bool:
    if ext_list is None:
        ext_list = {}
    folder = len(ext_list) == 0
    if path is None or not os.path.exists(path):
        print(f"Failed to find {name}, Please make sure path is correct.")
        return False
    elif folder and os.path.isfile(path):
        print(f"Path given for {name} is that of a file, please select a folder.")
        return False
    elif not folder and os.path.isdir(path):
        print(f"Path given for {name} is that of a folder, please select a file.")
        return False
    elif not folder and path.split(".")[-1] not in ext_list:
        print(f"Found a file for {name}, however it wasn't of the accepted types: {ext_list}")
        return False
    return True


def save_json(path, obj: dict) -> None:
    if not ensure_path(path, "save_json_path"):
        raise FileNotFoundError("Failed to find folder to put json into, make sure you have the correct path")
    # set these to None and False to prevent them from modifying the output when loaded back up
    obj['list_of_json_to_run'] = None
    obj['save_json_only'] = False
    fp = open(os.path.join(path, f"config-{time.time()}.json"), "w")
    json.dump(obj, fp=fp, indent=4)
    fp.close()


def load_json(path, obj: dict) -> dict:
    if not ensure_path(path, "load_json_path", {"json"}):
        raise FileNotFoundError("Failed to find base model, make sure you have the correct path")
    with open(path) as f:
        json_obj = json.loads(f.read())
    print("loaded json, setting variables...")
    ui_name_scheme = {"pretrained_model_name_or_path": "base_model", "logging_dir": "log_dir",
                      "train_data_dir": "img_folder", "reg_data_dir": "reg_img_folder",
                      "output_dir": "output_folder", "max_resolution": "train_resolution",
                      "lr_scheduler": "scheduler", "lr_warmup": "warmup_lr_ratio",
                      "train_batch_size": "batch_size", "epoch": "num_epochs",
                      "save_at_n_epochs": "save_every_n_epochs", "num_cpu_threads_per_process": "num_workers",
                      "enable_bucket": "buckets", "save_model_as": "save_as", "shuffle_caption": "shuffle_captions",
                      "resume": "load_previous_save_state", "network_dim": "net_dim",
                      "gradient_accumulation_steps": "gradient_acc_steps", "output_name": "change_output_name",
                      "network_alpha": "alpha", "lr_scheduler_num_cycles": "cosine_restarts",
                      "lr_scheduler_power": "scheduler_power"}

    for key in list(json_obj):
        if key in ui_name_scheme:
            json_obj[ui_name_scheme[key]] = json_obj[key]
            if ui_name_scheme[key] in {"batch_size", "num_epochs"}:
                try:
                    json_obj[ui_name_scheme[key]] = int(json_obj[ui_name_scheme[key]])
                except ValueError:
                    print(f"attempting to load {key} from json failed as input isn't an integer")
                    quit(1)

    for key in list(json_obj):
        if obj["json_load_skip_list"] and key in obj["json_load_skip_list"]:
            continue
        if key in obj:
            if key in {"keep_tokens", "warmup_lr_ratio"}:
                json_obj[key] = int(json_obj[key]) if json_obj[key] is not None else None
            if key in {"learning_rate", "unet_lr", "text_encoder_lr"}:
                json_obj[key] = float(json_obj[key]) if json_obj[key] is not None else None
            if obj[key] != json_obj[key]:
                print_change(key, obj[key], json_obj[key])
                obj[key] = json_obj[key]
    print("completed changing variables.")
    return obj


def print_change(value, old, new):
    print(f"{value} changed from {old} to {new}")


def get_occurrence_of_tags(args):
    extension = args['caption_extension']
    img_folder = args['img_folder']
    output_folder = args['output_folder']
    occurrence_dict = {}
    print(img_folder)
    for folder in os.listdir(img_folder):
        print(folder)
        if not os.path.isdir(os.path.join(img_folder, folder)):
            continue
        for file in os.listdir(os.path.join(img_folder, folder)):
            if not os.path.isfile(os.path.join(img_folder, folder, file)):
                continue
            ext = os.path.splitext(file)[1]
            if ext != extension:
                continue
            get_tags_from_file(os.path.join(img_folder, folder, file), occurrence_dict)
    output_list = {k: v for k, v in sorted(occurrence_dict.items(), key=lambda item: item[1], reverse=True)}
    with open(os.path.join(output_folder, f"{args['change_output_name']}.txt"), "w") as f:
        f.write(f"Below is a list of keywords used during the training of {args['change_output_name']}:\n")
        for k, v in output_list.items():
            f.write(f"[{v}] {k}\n")


def get_tags_from_file(file, occurrence_dict):
    f = open(file)
    temp = f.read().replace(", ", ",").split(",")
    f.close()
    for tag in temp:
        if tag in occurrence_dict:
            occurrence_dict[tag] += 1
        else:
            occurrence_dict[tag] = 1


if __name__ == "__main__":
    main()
