#! /usr/bin/python

import os
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))

import sys
sys.path.append(SCRIPT_PATH + '/../src/')

import re;

import subprocess
import multiprocessing
import getpass
from time import gmtime, strftime
from dataspec import *

try:
    import basicdefines
    MODULE_BASICDEFINES = True;
    ASSEMBLERS_PATH_ROOT_ABS = basicdefines.ASSEMBLERS_PATH_ROOT_ABS;
    TOOLS_ROOT = basicdefines.TOOLS_ROOT;
except:
    MODULE_BASICDEFINES = False;
    ASSEMBLERS_PATH_ROOT_ABS = os.path.join(SCRIPT_PATH, 'assemblers/');
    TOOLS_ROOT = '%s' % (SCRIPT_PATH);

# Loman Simpson pipeline
# https://github.com/jts/nanopore-paper-analysis/blob/master/full-pipeline.make

ASSEMBLER_URL = 'https://github.com/jts/nanopore-paper-analysis.git'
ASSEMBLER_PATH = os.path.join(basicdefines.ASSEMBLERS_PATH_ROOT_ABS, 'LQS')
# ZIP_FILE = 'wgs-8.3rc2-Linux_amd64.tar.bz2'
# ZIP_PATH = os.path.join(basicdefines.ASSEMBLERS_PATH_ROOT_ABS, ZIP_FILE)
ASSEMBLER_BIN = os.path.join(ASSEMBLER_PATH, 'full-pipeline.make')
ASSEMBLER_NAME = 'LQS'
ASSEMBLER_RESULTS = 'contig-100.fa'
CREATE_OUTPUT_FOLDER = True
NANOCORRECT_PATH = '%s/nanocorrect/' % (ASSEMBLER_PATH);
NANOPOLISH_PATH = '%s/nanopolish/' % (ASSEMBLER_PATH);
BWAMEM_PATH =  '%s/bwa/' % (ASSEMBLER_PATH);
SAMTOOLS_PATH =  '%s/samtools/' % (ASSEMBLER_PATH);
CELERA_PATH = '%s/wgs-8.2/Linux-amd64/bin/' % (ASSEMBLER_PATH);

# FASTQ to FASTA converter supplied by IDBA
FQ2FA_BIN = os.path.join(ASSEMBLER_PATH, 'bin/fq2fa')

# DRY_RUN = True;
DRY_RUN = False;

### Logs messages to STDERR and an output log file if provided (opened elsewhere).
def log(message, fp_log=None):
    timestamp = strftime("%Y/%m/%d %H:%M:%S", gmtime());

    sys.stderr.write('[%s wrapper %s] %s\n' % (ASSEMBLER_NAME, timestamp, message))
    sys.stderr.flush();
    if (fp_log != None):
        fp_log.write('[%s wrapper %s] %s\n' % (ASSEMBLER_NAME, timestamp, message))
        fp_log.flush();

def execute_command(command, fp_log, dry_run=True):
    if (dry_run == True):
        # sys.stderr.write('Warning: dry_run == True\n');
#        sys.stderr.write('[%s wrapper] Executing (dryrun): "%s"\n' % (ASSEMBLER_NAME, command));
        log('Executing (dryrun): "%s".' % (command), fp_log);
    if (dry_run == False):
        # sys.stderr.write('[%s wrapper] Executing: "%s"\n' % (ASSEMBLER_NAME, command));
        log('Executing: "%s".' % (command), fp_log);
        subprocess.call(command, shell=True);
    # sys.stderr.write('\n');
    log('\n', fp_log);

def measure_command(measure_file):
    if (MODULE_BASICDEFINES == True):
        return basicdefines.measure_command(measure_file);
    else:
        sys.stderr.write('ERROR: Cgmemtime tool not found! Exiting.\n');
        exit(1);
        # return '/usr/bin/time --format "Command line: %%C\\nReal time: %%e s\\nCPU time: -1.0 s\\nUser time: %%U s\\nSystem time: %%S s\\nMaximum RSS: %%M kB\\nExit status: %%x" --quiet -o %s ' % measure_file;

def peek(fp, num_chars):
    data = fp.read(num_chars);
    if len(data) == 0:
        return '';
    fp.seek(num_chars * -1, 1);
    return data;

# Returns a single read from the given FASTA/FASTQ file.
# Parameter header contains only the header of the read.
# Parameter lines contains all lines of the read, which include:
# - header
# - seq
# - '+' if FASTQ
# - quals if FASTQ
# Parameter lines is an array of strings, each for one component.
# Please note that multiline FASTA/FASTQ entries (e.g. sequence line)
# will be truncated into one single line.
def get_single_read(fp):
    lines = [];
    
    line = fp.readline();
    header = line.rstrip();
    header_leading_char = '';
    if (len(header) > 0):
        sequence_separator = header[0];
        header_leading_char = header[0];
        header = header[1:];            # Strip the '>' or '@' sign from the beginning.
    else:
        return ['', []];
    
    next_char = peek(fp, 1);
    
    line_string = '';
    lines.append(header_leading_char + header);
    
    num_lines = 1;
    #while len(next_char) > 0 and next_char != sequence_separator or (next_char == '@' and num_lines < 4):
    while (len(next_char) > 0 and (next_char != sequence_separator or (next_char == '@' and num_lines < 4))):
        line = fp.readline();
        if (line.rstrip() == '+' or line.rstrip() == ('+' + header)):
        #if (line.rstrip()[0] == '+'):
            lines.append(line_string);
            lines.append(line.rstrip());
            line_string = '';
        else:
            line_string += line.rstrip();
        next_char = peek(fp, 1);
        num_lines += 1;
        
    lines.append(line_string);
    
    return [header, lines];

def convert_to_fasta(fastq_path, out_fasta_path):
    fp_in = None;
    fp_out = None;
    
    try:
        fp_in = open(fastq_path, 'r');
    except IOError:
        print 'ERROR: Could not open file "%s" for reading!' % fastq_path;
        return;
    
    try:
        fp_out = open(out_fasta_path, 'w');
    except IOError:
        print 'ERROR: Could not open file "%s" for writing!' % out_fasta_path;
        fp_in.close();
        return;
    
    while True:
        [header, read] = get_single_read(fp_in);
        if (len(header) == 0):
            break;
        seq = read[1];
        fp_out.write('>' + header + '\n');
        fp_out.write(seq + '\n');
    fp_in.close();
    fp_out.close();

# Finds all files with a given filename pattern starting from the given path, recursivelly.
def find_files(start_path, file_pattern, max_depth=-1):
    matches = []
    for root, dirnames, filenames in os.walk(start_path):
        for filename in fnmatch.filter(filenames, file_pattern):
            depth = len(root.split('/'))
            if (max_depth < 0 or (max_depth >= 0 and depth <= max_depth)):
                matches.append(os.path.join(root, filename))

    matches.sort()
    return matches

# Simply lists all subfolders, recursivelly. Parameter 'depth' can be used to specify the minimum depth of the subfolders.
def find_folders(start_path, depth=0):
    matches = []
    for x in os.walk(start_path):
        if (len(x[0].split('/')) >= depth):
            matches.append(x[0])
    return matches

##############################################################
##############################################################
##############################################################
def parse_memtime(memtime_path):
    cmdline = '';
    realtime = 0;
    cputime = 0;
    usertime = 0;
    systemtime = 0;
    maxrss = 0;
    rsscache = 0;
    time_unit = '';
    mem_unit = '';

    try:
        fp = open(memtime_path, 'r');
        lines = [line.strip() for line in fp.readlines() if (len(line.strip()) > 0)];
        fp.close();
    except Exception, e:
        sys.stderr.write('Could not find memory and time statistics in file "%s".\n' % (memtime_path));
        return [cmdline, realtime, cputime, usertime, systemtime, maxrss, time_unit, mem_unit];

    for line in lines:
        if (line.startswith('Command line:')):
            cmdline = line.split(':')[1].strip();
        elif (line.startswith('Real time:')):
            split_line = line.split(':')[1].strip().split(' ');
            realtime = float(split_line[0].strip());
            time_unit = split_line[1].strip();
        elif (line.startswith('CPU time:')):
            split_line = line.split(':')[1].strip().split(' ');
            cputime = float(split_line[0].strip());
            time_unit = split_line[1].strip();
        elif (line.startswith('User time:')):
            split_line = line.split(':')[1].strip().split(' ');
            usertime = float(split_line[0].strip());
            time_unit = split_line[1].strip();
        elif (line.startswith('System time:')):
            split_line = line.split(':')[1].strip().split(' ');
            systemtime = float(split_line[0].strip());
            time_unit = split_line[1].strip();
        elif (line.startswith('Maximum RSS:')):
            split_line = line.split(':')[1].strip().split(' ');
            maxrss = float(split_line[0].strip());
            mem_unit = split_line[1].strip();
        # elif (line.startswith('')):
        #   split_line = line.split(':')[1].strip().split(' ');
        #   rsscache = float(split_line[0].strip());
        #   mem_unit = split_line[1].strip();

    return [cmdline, realtime, cputime, usertime, systemtime, maxrss, time_unit, mem_unit];

def parse_memtime_files_and_accumulate(memtime_files, final_memtime_file):
    final_command_line = '';
    final_real_time = 0.0;
    final_cpu_time = 0.0;
    final_user_time = 0.0;
    final_system_time = 0.0;
    final_time_unit = '';
    final_max_rss = 0;
    final_mem_unit = '';

    i = 0;
    for memtime_file in memtime_files:
        i += 1;
        sys.stderr.write('Parsing memtime file "%s"...\n' % (memtime_file));

        [cmdline, realtime, cputime, usertime, systemtime, maxrss, time_unit, mem_unit] = parse_memtime(memtime_file);
        if (i == 1):
            final_command_line = cmdline;
            final_real_time = realtime;
            final_cpu_time = cputime;
            final_user_time = usertime;
            final_system_time = systemtime;
            final_max_rss += maxrss;
            final_time_unit = time_unit;
            final_mem_unit = mem_unit;
        else:
            if (time_unit == final_time_unit and mem_unit == final_mem_unit):
                final_command_line += '; ' + cmdline;
                final_real_time += realtime;
                final_cpu_time += cputime;
                final_user_time += usertime;
                final_system_time += systemtime;
                final_max_rss += maxrss;
            else:
                sys.stderr.write('Memory or time units not the same in all files! Instead of handling this, we decided to be lazy and just give up.\n');
                break;

    try:
        fp = open(final_memtime_file, 'w');
    except Exception, e:
        sys.stderr.write('ERROR: Could not open file "%s" for writing!\n' % (final_memtime_file));
        return;

    if (final_cpu_time <= 0.0):
        final_cpu_time = final_user_time + final_system_time;

    fp.write('Command line: %s\n' % (final_command_line));
    fp.write('Real time: %f %s\n' % (final_real_time, final_time_unit));
    fp.write('CPU time: %f %s\n' % (final_cpu_time, final_time_unit));
    fp.write('User time: %f %s\n' % (final_user_time, final_time_unit));
    fp.write('System time: %f %s\n' % (final_system_time, final_time_unit));
    fp.write('Maximum RSS: %f %s\n' % (final_max_rss, final_mem_unit));

    fp.close();


# Function 'run' should provide a standard interface for running a mapper. Given input parameters, it should run the
# alignment process, and convert any custom output results to the SAM format. Function should return a string with the
# path to the output file.
#    reads_file            Path to a FASTA/FASTQ file containing reads.
#    reference_file        Path to a reference genome FASTA file.
#    machine_name        A symbolic name to specify a set of parameters for a specific sequencing platform.
#    output_path            Folder to which the output will be placed to. Filename will be automatically generated according to the name of the mapper being run.
#    output_suffix        A custom suffix that can be added to the output filename.
# def run(reads_files, reference_file, machine_name, output_path, output_suffix=''):
def run(datasets, output_path):
    ### make -f full-pipeline.make CORES=64 polished_genome.fasta

    ##################################################################################
    ### Sanity check for input datasets.
    ##################################################################################    
    machine_name = None
    for dataset in datasets:
        if (machine_name != None and dataset.type != machine_name):
            sys.stderr.write('ERROR: %s is not a hybrid assembler, but datasets from disparate technologies are specified! Exiting.\n');
            exit(1);
        machine_name = dataset.type;
    if (machine_name == None):
        sys.stderr.write('ERROR: Input datasets not specified correctly! Exiting.\n');
        exit(1);

    ##################################################################################
    ### Simple variable definitions.
    ##################################################################################        
    num_cores = 16;
    num_threads = 4;
    output_path = os.path.abspath(output_path);
    raw_reads_path = '%s/raw.reads.fasta' % (output_path);
    raw_reads_filename = os.path.basename(raw_reads_path);
    raw_reads_basename = os.path.splitext(os.path.basename(raw_reads_path))[0];

    ##################################################################################
    ### Prepare a log file.
    ##################################################################################
    log_file = '%s/wrapper_log.txt' % (output_path);
    try:
        fp_log = open(log_file, 'a');
    except Exception, e:
        log('ERROR: Could not open file "%s" for writing! Using only STDERR for logging.' % (log_file), None);
        fp_log = None;

    ##################################################################################
    ### Check if permissions are given for Cgmemtime.
    ##################################################################################
    if (MODULE_BASICDEFINES == True):
        execute_command('%s ls -lhrt' % (measure_command('%s/test.memtime' % output_path)), fp_log, dry_run=DRY_RUN);
        if (not os.path.exists('%s/test.memtime' % (output_path))):
            command = 'sudo %s/cgmemtime/cgmemtime --setup -g %s --perm 775' % (basicdefines.TOOLS_ROOT, getpass.getuser());
            sys.stderr.write('[] %s\n' % (command));
            execute_command(command, fp_log, dry_run=DRY_RUN);

    ##################################################################################
    ### Backup old assembly results, and create the new output folder.
    ##################################################################################
    ### This part is a little bit different than for other wrappers, basically just because
    ### this pipeline takes a long time to run, and sometimes the user might wish to run
    ### only a part of the pipeline. In this case, the output folder should not be moved.
    ### In case only polishing needs to be run, don't move the output folder to a different location.
    if (machine_name == 'nanopore' or machine_name == 'correct1'):
        ### Backup old assembly results, and create the new output folder.
        if (os.path.exists(output_path)):
            timestamp = strftime("%Y_%m_%d-%H_%M_%S", gmtime());
            os.rename(output_path, '%s.bak_%s' % (output_path, timestamp));
        if (not os.path.exists(output_path)):
            log('Creating a directory on path "%s".' % (output_path), None);
            os.makedirs(output_path);

    ##################################################################################
    ### Preparing the input datasets.
    ##################################################################################
    log('Preparing the input datasets.\n', fp_log);

    ### Collect all reads paths, including the folders one level up (because of the design of this benchmarking framework, raw FAST5 files will be located in a folder one level up).
    reads_folders = [];
    folders_one_level_up = [];
    for single_reads_file in reads_files:
        # if (reads_folder == None):
        reads_folder = os.path.dirname(single_reads_file);
        reads_folders.append(reads_folder);
        reads_basename = os.path.basename(single_reads_file);

        folder_one_level_up = '/'.join(reads_folder.split('/')[0:-1]);
        folders_one_level_up.append(folder_one_level_up);
        reads_folders.append(folder_one_level_up);

    ### In case only polishing needs to be run, don't create the joined FASTA file again, but leave the one which was generated before.
    if (machine_name == 'nanopore' or machine_name == 'correct1'):
        ### If more than one file given, they will be joined into this file (reads_file).
        ### Making sure that the file can be opened for writing, and emptying it in the process.
        reads_file = os.path.abspath('%s/joint_reads' % (output_path));
        try:
            fp = open(reads_file, 'w');
            fp.close();
        except:
            log('ERROR: Could not open file "%s" for writing!\n' % (reads_file), None);
            return;
        ### Concatenating the reads into a single file.
        log('Preparing raw reads.', None);
        i = 0;
        for single_reads_file in reads_files:
            i += 1;
            single_reads_file = os.path.abspath(single_reads_file);
            execute_command('cat %s >> %s' % (single_reads_file, reads_file), None, dry_run=DRY_RUN);
            log('\t(%d) %s -> %s' % (i, single_reads_file, reads_file), None);

        ### Backup the old file if it existed.
        if (os.path.exists(raw_reads_path) == True):
            os.rename(raw_reads_path, raw_reads_path + '.bak');
        ### Convert the reads file to FASTA format.
        ### Generate a raw reads file in the output folder, which will be used for assembly.
        convert_to_fasta(reads_file, raw_reads_path);

    ##################################################################################
    ### Start the important work.
    ##################################################################################
    log('Running assembly using %s.' % (ASSEMBLER_NAME), fp_log);

    if (machine_name == 'illumina'):
        log('\nMachine name "%s" not implemented for %s.\n' % (machine_name, ASSEMBLER_NAME));
        log('Skipping ....\n', fp_log)
        return;
    elif (machine_name == 'pacbio'):
        log('\nMachine name "%s" not implemented for %s.\n' % (machine_name, ASSEMBLER_NAME));
        log('Skipping ....\n', fp_log)
        return;

    if (MODULE_BASICDEFINES == True):
        execute_command('%s/cgmemtime/cgmemtime -o %s/test.memtime ls -lhrt' % (basicdefines.TOOLS_ROOT, output_path), fp_log, dry_run=DRY_RUN);
        if (not os.path.exists('%s/test.memtime' % (output_path))):
            command = 'sudo %s/cgmemtime/cgmemtime --setup -g %s --perm 775' % (basicdefines.TOOLS_ROOT, getpass.getuser());
            sys.stderr.write('[] %s\n' % (command));
            execute_command(command, fp_log, dry_run=DRY_RUN);

    memtime_file = '%s/%s.memtime' % (output_path, ASSEMBLER_NAME);
    # memtime_files_prefis = 
    memtime_files_prefix =  '%s/%s' % (output_path, ASSEMBLER_NAME);

    commands = [];
    commands.append('cd %s' % (output_path));
    # The programs we will install must be on the PATH
    commands.append('export PATH=%s/DAZZ_DB:%s/DALIGNER:%s/nanocorrect:%s/poaV2:%s/wgs-8.2/Linux-amd64/bin/:%s/samtools/:%s/bwa/:%s/:$PATH' % (ASSEMBLER_PATH, ASSEMBLER_PATH, ASSEMBLER_PATH, ASSEMBLER_PATH, ASSEMBLER_PATH, ASSEMBLER_PATH, ASSEMBLER_PATH, ':'.join(reads_folders)));
    # Parameters to control execution
    commands.append('CORES=%d' % (num_cores));
    commands.append('THREADS=%d' % (num_threads));
    commands.append('NC_PROCESS=%d' % (num_cores));
    commands.append('NP_PROCESS=%d' % (num_cores / num_threads));

    commands.append('LS_ENV=%s/ls_env' % (ASSEMBLER_PATH));
    commands.append('. $LS_ENV/bin/activate');

    current_memtime_id = 0;

    ### Create symlinks to folders with reads, their parent folders, and subfolders of those folders.
    reads_folders = sorted(set(reads_folders));
    # reads_folders2 = find_folders(folders_one_level_up)
    for folder in reads_folders:
        temp_folders = find_folders(folder, depth=0);
        for temp_folder in temp_folders:
            commands.append('unlink %s' % (os.path.basename(temp_folder)));
            commands.append('ln -s %s' % (temp_folder));

    ### Run error correction.
    if (machine_name == 'nanopore' or machine_name == 'correct1' or machine_name == 'nopolish'):
        # Error correction, the first step.
        current_memtime_id = 0;

        current_memtime_id += 1;
        commands.append('%s make -f %s/nanocorrect-overlap.make INPUT=%s NAME=%s' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOCORRECT_PATH, raw_reads_path, raw_reads_basename));
        current_memtime_id += 1;
        commands.append('%s samtools faidx %s.pp.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), raw_reads_basename));
        current_memtime_id += 1;
        commands.append('%s bash -c "python %s/makerange.py %s | parallel -v --eta -P $NC_PROCESS \'python %s/nanocorrect.py %s {} > %s.{}.corrected.fasta\'"' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOCORRECT_PATH, raw_reads_path, NANOCORRECT_PATH, raw_reads_basename, raw_reads_basename));
        current_memtime_id += 1;
        commands.append('%s bash -c "cat %s.*.corrected.fasta | python %s/lengthsort.py > %s.corrected.fasta"' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), raw_reads_basename, ASSEMBLER_PATH, raw_reads_basename));

    if (machine_name == 'nanopore' or machine_name == 'correct2' or machine_name == 'nopolish'):
        #rm raw.reads.*.corrected.fasta
        # Error correction, the second step.
        current_memtime_id = 4;

        current_memtime_id += 1;
        commands.append('%s make -f %s/nanocorrect-overlap.make INPUT=%s.corrected.fasta NAME=%s.corrected' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOCORRECT_PATH, raw_reads_basename, raw_reads_basename));
        current_memtime_id += 1;
        commands.append('%s samtools faidx %s.corrected.pp.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), raw_reads_basename));
        current_memtime_id += 1;
        commands.append('%s bash -c "python %s/makerange.py %s.corrected.fasta | parallel -v --eta -P $NC_PROCESS \'python %s/nanocorrect.py %s.corrected {} > %s.corrected.{}.corrected.fasta\'"' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOCORRECT_PATH, raw_reads_basename, NANOCORRECT_PATH, raw_reads_basename, raw_reads_basename));
        current_memtime_id += 1;
        commands.append('%s bash -c "cat %s.corrected.*.corrected.fasta | python %s/lengthsort.py > %s.corrected.corrected.fasta"' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), raw_reads_basename, ASSEMBLER_PATH, raw_reads_basename));
        # commands.append('rm raw.reads.corrected.*.corrected.fasta');

    if (machine_name == 'nanopore' or machine_name == 'celera' or machine_name == 'nopolish'):
        current_memtime_id = 8;

        reads_error_corrected = 'raw.reads.corrected.corrected.fasta';
        reads_assembly_input = 'assembly.input.fastq';
        current_memtime_id += 1;
        commands.append('%s java -Xmx1024M -jar %s/convertFastaAndQualToFastq.jar %s > %s' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), CELERA_PATH, reads_error_corrected, reads_assembly_input));
        current_memtime_id += 1;
        commands.append('%s fastqToCA -technology sanger -libraryname assembly -reads %s > assembly.frg' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), reads_assembly_input));
        current_memtime_id += 1;
        commands.append('%s runCA -d celera-assembly -p asm -s %s/revised_ovlErrorRate0.04.spec assembly.frg' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), ASSEMBLER_PATH));
        current_memtime_id += 1;
        commands.append('%s ln -s celera-assembly/9-terminator/asm.scf.fasta draft_genome.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id))));

    if (machine_name == 'nanopore' or machine_name == 'polish'):
        current_memtime_id = 12;

        commands.append('pwd');
        commands.append('%s ln -s celera-assembly/9-terminator/asm.scf.fasta draft_genome.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id))));
        # preprocess the fasta file for nanopolish
        current_memtime_id += 1;
        commands.append('%s %s/scripts/consensus-preprocess.pl %s > %s.np.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOPOLISH_PATH, raw_reads_path, raw_reads_basename));
        # index the draft assembly for bwa
        current_memtime_id += 1;
        commands.append('%s %s/bwa index draft_genome.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), BWAMEM_PATH));
        # index the draft assembly for faidx
        current_memtime_id += 1;
        commands.append('%s %s/samtools faidx draft_genome.fasta' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), SAMTOOLS_PATH));
        # align reads to draft assembly
        current_memtime_id += 1;
        commands.append('%s bash -c "%s/bwa mem -t $THREADS -x ont2d draft_genome.fasta %s.np.fasta | %s/samtools view -Sb - | %s/samtools sort -f - reads_to_draft.sorted.bam"' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), BWAMEM_PATH, raw_reads_basename, SAMTOOLS_PATH, SAMTOOLS_PATH));
        # index the bam file
        current_memtime_id += 1;
        commands.append('%s %s/samtools index reads_to_draft.sorted.bam' % (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), SAMTOOLS_PATH));
        # run nanopolish
        current_memtime_id += 1;
        # commands.append('bash -c "python %s/scripts/nanopolish_makerange.py %s/draft_genome.fasta | parallel --progress -P $NP_PROCESS %s/nanopolish consensus -o %s/nanopolish.{1}.fa -r %s/%s.np.fasta -b %s/reads_to_draft.sorted.bam -g %s/draft_genome.fasta -w {1} -t $THREADS python %s/scripts/nanopolish_merge.py %s/draft_genome.fasta %s/nanopolish.scf*.fa > polished_genome.fasta"' %
        #                 (NANOPOLISH_PATH, output_path, NANOPOLISH_PATH, output_path, output_path, raw_reads_basename, output_path, output_path, NANOPOLISH_PATH, output_path, output_path));

        # commands.append('ls -lhrt ERX708231.fast5/LomanLabz_PC_K12_0.4SPRI_Histag_2004_1_ch433_file81_strand.fast5; echo $PATH');
        commands.append('%s bash -c "python %s/scripts/nanopolish_makerange.py %s/draft_genome.fasta | parallel --progress -P $NP_PROCESS %s/nanopolish consensus -o %s/nanopolish.{1}.fa -r %s/%s.np.fasta -b %s/reads_to_draft.sorted.bam -g %s/draft_genome.fasta -w {1} -t $THREADS"' %
                        (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOPOLISH_PATH, output_path, NANOPOLISH_PATH, output_path, output_path, raw_reads_basename, output_path, output_path));
        current_memtime_id += 1;
        commands.append('%s python %s/scripts/nanopolish_merge.py %s/draft_genome.fasta %s/nanopolish.scf*.fa > polished_genome.fasta' %
                        (measure_command('%s-%s.memtime' % (memtime_files_prefix, current_memtime_id)), NANOPOLISH_PATH, output_path, output_path));

        commands.append('cp %s/polished_genome.fasta %s/benchmark-final_assembly.fasta' % (output_path, output_path));

    command = '; '.join(commands);
    execute_command(command, None, dry_run=DRY_RUN);

    ##################################################################################
    ### Accumulate the memtime stats.
    ##################################################################################
    all_memtimes = ['%s-%s.memtime' % (memtime_files_prefix, value) for value in xrange(1, current_memtime_id)];
    parse_memtime_files_and_accumulate(all_memtimes, memtime_file);

    if (fp_log != None):
        fp_log.close();

    # Atm, quast is run in the main program


# A placeholder for a function that runs quast on assembly results
# This is the same for all wrappers at the moment and is done in the main program
def run_quast():
    pass

# A function that gets the results of cgmemtime for a wrapper
# Since some aligners are run multiple times and create multiple measurements
# this is specific for each wrapper
# Returns relevant real time, user time and maximum memory reserved
def get_memtime():
    pass


# This is a standard interface for setting up an assembler. It should assume that the assembler
# is not present localy, but needs to be retrieved, unpacked, compiled and set-up, without requireing
def download_and_install():
    if os.path.exists(ASSEMBLER_BIN):
        # sys.stderr.write('[%s wrapper] Bin found at %s. Skipping installation.\n' % (ASSEMBLER_NAME, ASSEMBLER_BIN))
        log('Bin found at %s. Skipping installation.' % (ASSEMBLER_BIN), None);

    else:
        # sys.stderr.write('[%s wrapper] Started installation of %s.\n' % (ASSEMBLER_NAME, ASSEMBLER_NAME))
        log('Started installation of %s.' % (ASSEMBLER_NAME), None);
        if (not os.path.exists(ASSEMBLER_PATH)):
            # sys.stderr.write('[%s wrapper] Creating a directory on path "%s".\n' % (ASSEMBLER_NAME, ASSEMBLERS_PATH_ROOT_ABS))
            log('Creating a directory on path "%s".' % (ASSEMBLER_PATH), None);
            os.makedirs(ASSEMBLER_PATH);

        # command = 'cd %s; git clone %s' % (ASSEMBLERS_PATH_ROOT_ABS, ASSEMBLER_URL)
        # execute_command(command, None, dry_run=DRY_RUN);

        setup_commands = [];
        # The programs we will install must be on the PATH');
        # Install the BioPerl dependency, as well as other dependencies.
        setup_commands.append('cd %s' % (ASSEMBLER_PATH));
        setup_commands.append('sudo apt-get install bioperl');
        setup_commands.append('sudo apt-get install parallel');
        setup_commands.append('sudo apt-get install ncurses-dev');
        setup_commands.append('sudo apt-get install libhdf5-dev');
        setup_commands.append('sudo apt-get install r-base');
        setup_commands.append('sudo pip install virtualenv');
        # Install Python dependencies.
        setup_commands.append('LS_ENV=%s/ls_env' % (ASSEMBLER_PATH));
        setup_commands.append('virtualenv --no-site-packages --always-copy $LS_ENV');
        # Activate the virtual environment.
        setup_commands.append('. $LS_ENV/bin/activate');
        # Install the required Python packages in the virtual environment.
        setup_commands.append('pip install rpy2');
        setup_commands.append('pip install --upgrade setuptools');
        setup_commands.append('pip install pysam > pythonlibs.version');
        setup_commands.append('pip install cython >> pythonlibs.version');
        setup_commands.append('pip install numpy==1.8.1 >> pythonlibs.version');
        setup_commands.append('pip install h5py==2.3.0 >> pythonlibs.version');
        setup_commands.append('pip install cython >> pythonlibs.version');
        setup_commands.append('pip install poretools >> pythonlibs.version');
        setup_commands.append('pip install biopython >> pythonlibs.version');
        setup_commands.append('pip freeze >> pythonlibs.version');
        setup_commands.append('pip install biopython --upgrade');

        # Install samtools
        setup_commands.append('git clone --recursive https://github.com/samtools/htslib.git');
        setup_commands.append('cd htslib; make; cd ..');
        setup_commands.append('git clone --recursive https://github.com/samtools/samtools.git');
        setup_commands.append('cd samtools; make; cd ..');
        setup_commands.append('cd samtools; git log | head -1 > ../samtools.version');
        setup_commands.append('cd ..');
        # Install nanocorrect & dependencies
        setup_commands.append('git clone https://github.com/jts/nanocorrect.git');
        setup_commands.append('ln -s nanocorrect/poa-blosum80.mat');
        # setup_commands.append('cd nanocorrect; git checkout 47dcd7f147c; git log | head -1 > ../nanocorrect.version'); ### This commit was used in the LQS paper.
        setup_commands.append('cd nanocorrect; git checkout 0cc9da028156a14892ed592163f647822fe21792; git log | head -1 > ../nanocorrect.version'); ### Commit from Date:   Thu Nov 5 09:15:04 2015 -0500 .

        setup_commands.append('cd ..');
        # Install nanopolish, automatically downloading libhdf5
        setup_commands.append('git clone --recursive https://github.com/jts/nanopolish.git');
        # setup_commands.append('cd nanopolish; git checkout 6440bfbfcf4fa; make libhdf5.install nanopolish; cd ..'); ### This commit was used in the LQS paper.
        setup_commands.append('cd nanopolish; git checkout b1808594f67066256f4c5712995d51f72b8efa9f; make; cd ..'); ### Commit from Date:   Wed Nov 4 11:15:14 2015 -0500 .
        # setup_commands.append('cd nanopolish; make libhdf5.install nanopolish; cd ..');
        setup_commands.append('cd nanopolish; git log | head -1 > ../nanopolish.version');
        setup_commands.append('cd ..');
        # Install bwa
        setup_commands.append('git clone https://github.com/lh3/bwa.git');
        setup_commands.append('cd bwa; make');
        setup_commands.append('cd bwa; git log | head -1 > ../bwa.version');
        setup_commands.append('cd ..');
        # Install poa
        setup_commands.append('wget http://downloads.sourceforge.net/project/poamsa/poamsa/2.0/poaV2.tar.gz');
        setup_commands.append('tar -xzf poaV2.tar.gz');
        setup_commands.append('cd poaV2; make CFLAGS=\'-O3 -g -DUSE_WEIGHTED_LINKS -DUSE_PROJECT_HEADER -I.\' poa');
        setup_commands.append('cd ..');
        setup_commands.append('ln -s poaV2/poa');
        setup_commands.append('echo http://downloads.sourceforge.net/project/poamsa/poamsa/2.0/poaV2.tar.gz > poa.version');
        # Install DALIGNER
        setup_commands.append('git clone https://github.com/thegenemyers/DALIGNER.git');
        setup_commands.append('cd DALIGNER; git checkout 549da77b91395dd; make; cd ..');
        setup_commands.append('echo "549da77b91395dd" > daligner.version');
        # Install DAZZ_DB
        setup_commands.append('git clone https://github.com/thegenemyers/DAZZ_DB');
        setup_commands.append('cd DAZZ_DB; git checkout 8cb2f29c4011a2c2; make; cd ..');
        setup_commands.append('echo "8cb2f29c4011a2c2" > dazz_db.version');
        # Install Celera Assembler
        setup_commands.append('wget http://downloads.sourceforge.net/project/wgs-assembler/wgs-assembler/wgs-8.2/wgs-8.2-Linux_amd64.tar.bz2');
        setup_commands.append('tar -xjf wgs-8.2-Linux_amd64.tar.bz2');
        setup_commands.append('wget http://www.cbcb.umd.edu/software/PBcR/data/convertFastaAndQualToFastq.jar');
        setup_commands.append('mv convertFastaAndQualToFastq.jar wgs-8.2/Linux-amd64/bin/');
        setup_commands.append('echo http://downloads.sourceforge.net/project/wgs-assembler/wgs-assembler/wgs-8.2/wgs-8.2-Linux_amd64.tar.bz2 > ca.version');
        # Install lengthsort.
        setup_commands.append('wget https://raw.githubusercontent.com/jts/nanopore-paper-analysis/master/lengthsort.py');
        setup_commands.append('echo "lengthsort" > lengthsort.version');
        # Download the spec file for Celera.
        setup_commands.append('wget --no-check-certificate https://raw.githubusercontent.com/jts/nanopore-paper-analysis/c25373d93a99e51c2fedb57d8b08b81826e7c80c/revised_ovlErrorRate0.04.spec');

        command = '; '.join(setup_commands);
        execute_command(command, None, dry_run=DRY_RUN);



# def verbose_usage_and_exit():
#     sys.stderr.write('Usage:\n')
#     sys.stderr.write('\t%s mode [<reads_file1>,<reads_file2>,...,<reads_fileN> <machine_name> <output_path> <reference_file> [<output_suffix>]]\n' % sys.argv[0])
#     sys.stderr.write('\n')
#     sys.stderr.write('\t- mode - either "run" or "install". Is "install" other parameters can be ommitted.\n')

#     exit(0)

# if __name__ == "__main__":
#     if (len(sys.argv) < 2 or len(sys.argv) > 7):
#         verbose_usage_and_exit()

#     if (sys.argv[1] == 'install'):
#         download_and_install()
#         exit(0)

#     elif (sys.argv[1] == 'run'):
#         if (len(sys.argv) < 5 or len(sys.argv) > 7):
#             verbose_usage_and_exit()

#         reads_files = sys.argv[2].split(',')         ### Enable specifying multiple FASTQ files for input.
#         machine_name = sys.argv[3]
#         output_path = sys.argv[4]
#         reference_file = '';
#         output_suffix = ''

#         if (len(sys.argv) >= 6):
#             reference_file = sys.argv[5]
#         if (len(sys.argv) == 7):
#             output_suffix = sys.argv[6]
#         run(reads_files, reference_file, machine_name, output_path, output_suffix)

#     else:
#         verbose_usage_and_exit()

def verbose_usage_and_exit():
    sys.stderr.write('Usage:\n')
    # sys.stderr.write('\t%s mode [<reads_file1>,<reads_file2>,...,<reads_fileN> <machine_name> <output_path>]\n' % sys.argv[0])
    sys.stderr.write('\t%s mode [<output_path> dataset1 [dataset2 ...]]\n' % sys.argv[0])
    sys.stderr.write('\n')
    sys.stderr.write('\t- mode - either "run" or "install". If "install" other parameters can be omitted.\n')
    sys.stderr.write('\t- dataset - specification of a dataset in the form: reads_type,<reads_path>[<reads_path_b,frag_len,frag_stddev] .\n');
    sys.stderr.write('\t            Reads_type can be nanopore/pacbio/single/paired/mate. If reads_type == "paired" or "mate", last three parameters can be omitted".\n');
    sys.stderr.write('\t            If reads_type == "paired" or "mate", other end of the pair needs to be in another file provided by reads_path_b.\n');
    sys.stderr.write('\n');
    sys.stderr.write('Additional reads_type for LQS pipeline include: nanopore, correct1, correct2, nopolish, celera, polish.\n');

    sys.stderr.write('Example:\n');
    sys.stderr.write('\t%s run results/%s nanopore,datasets/reads.fastq\n' % (os.path.basename(sys.argv[0]), ASSEMBLER_NAME));
    sys.stderr.write('\n');

    exit(0)

if __name__ == "__main__":
    if (len(sys.argv) < 2 or len(sys.argv) > 7):
        verbose_usage_and_exit()

    if (sys.argv[1] == 'install'):
        download_and_install()
        exit(0)

    elif (sys.argv[1] == 'run'):
        if (len(sys.argv) < 4):
            verbose_usage_and_exit()

        output_path = sys.argv[2]
        datasets = [];
        for arg in sys.argv[3:]:
            dataset = Dataset(arg);
            datasets.append(dataset);
        run(datasets, output_path);

    else:
        verbose_usage_and_exit()