#! /bin/env python

# Python imports
import os, sys, stat, argparse, getpass, json
from datetime import datetime
from math import sqrt
import yaml
from collections import OrderedDict
from subprocess import call

# to prevent pyroot to hijack argparse we need to go around
tmpargv = sys.argv[:] 
sys.argv = []

# ROOT imports
import ROOT
ROOT.gROOT.SetBatch()
ROOT.PyConfig.IgnoreCommandLineOptions = True
sys.argv = tmpargv

hadNegBinForProcess = {}
hadNegBinErrForProcess = {}
def setNegativeBinsToZero(h, process):
    if not process in hadNegBinForProcess:
        hadNegBinForProcess[process] = False
    for i in range(1, h.GetNbinsX() + 1):
        if h.GetBinContent(i) < 0.:
            if not hadNegBinForProcess[process]:
                print 'Remove negative bin in TH1 %s for process %s'%(h.GetTitle(), process)
            hadNegBinForProcess[process] = True
            h.SetBinContent(i, 0.)
    
def get_hist_regex(r):
    return '^%s(__.*(up|down))?$' % r

cmssw_base = os.environ['CMSSW_BASE']

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1', 'True'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0', 'False'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

parser = argparse.ArgumentParser(description='Create shape datacards ready for combine')

parser.add_argument('-p', '--path', action='store', dest='root_path', type=str, default=cmssw_base+'/src/UserCode/FCNCLimits/histos_suitable_for_limits_200101_2017/training_0101010101', help='Directory containing rootfiles with the TH1 used for limit settings')
parser.add_argument('-l', '--luminosity', action='store', type=float, dest='luminosity', default=41529, help='Integrated luminosity (default is 41529 /pb)')
parser.add_argument('-le', '--luminosityError', action='store', type=float, dest='luminosityError', default=1.023, help='Error on the integrated luminosity (default is 1.023 /pb)')
parser.add_argument('-o', '--output', action='store', dest='output', type=str, default='datacards_200101_2017', help='Output directory')
parser.add_argument('-c' , '--channel', action='store', dest='channel', type=str, default='all', help='Channel: el, mu, or all.')
parser.add_argument('-applyxsec' , action='store', dest='applyxsec', type=bool, default=True, help='Reweight MC processes by Xsec/Nevt from yml config.')
parser.add_argument('-xsecfile' , action='store', dest='xsecfile', type=str, default='files_17.yml', help='YAML config file path with Xsec and Nevt.')
parser.add_argument('--nosys', action='store', dest='nosys', default=False, help='Consider or not systematic uncertainties (NB : bbb uncertainty is with another flag)')
parser.add_argument('--sysToAvoid', action='store', dest='sysToAvoid', nargs='+', default=['tauidjetHighptstat'], help='Set it to exclude some of the systematics. Name should as in rootfile without the up/dowm postfix')
# Example to call it: python prepareShapesAndCards.py --sysToAvoid pu hf

parser.add_argument('--sysForSMtt', action='store', dest='sysForSMtt', nargs='+', default=[ 'isr','fsr', 'pdfalphas','mescale','renscale','facscale','tune','hdamp'], help='Systematics affecting only SM tt.')
parser.add_argument('--sysForSig', action='store', dest='sysForSig', nargs='+', default=['isr','fsr','mescale','renscale','facscale'], help='Systematics affecting Signals (must be common with SMtt)')
parser.add_argument('--correlatedSys', action='store', dest='correlatedSys', nargs='+', default=['muid','muiso','mutrg','pu', 'isr','fsr', 'pdfalphas','mescale','renscale','facscale','tune','hdamp'], help='Systematics that are correlated accross years. NB: cross section unc are added by hand at the end of this script, go there to change correlation for them.')

parser.add_argument('-rebinning' , action='store', dest='rebinning', type=int, default=4, help='Rebin the histograms by -rebinning.')
parser.add_argument('-dataYear' , action='store', dest='dataYear', type=str, default='2017', help='Which year were the data taken? This has to be added in datacard entries in view of combination (avoid considering e.g. correlated lumi uncertainty accross years)')

options = parser.parse_args()

correlatedSys = options.correlatedSys
correlatedSys.extend(['jesAbsolute', 'jesAbsolute_'+options.dataYear, 'jesBBEC1', 'jesBBEC1_'+options.dataYear, 'jesFlavorQCD', 'jesRelativeBal', 'jesRelativeSample_'+options.dataYear, 'jesHEM'])

correlatedSys.extend(['btagcferr1','btagcferr2','btaghf','btaglf'])
correlatedSys.extend(['tauidjetHighptextrap','tauidjetHighptsyst','tauidjetSystalleras'])
correlatedSys.extend(['pdf'+str(i) for i in range(1,51)])

sysForSMtt = options.sysForSMtt
sysForSMtt.extend(['pdf'+str(i) for i in range(1,51)])

sysForSig = options.sysForSig
sysForSig.extend(['pdf'+str(i) for i in range(1,51)])

print("LIST OF sysForSig : " , sysForSig)


years = {'2016pre': 19502, '2016post': 16812, '2017': 41480, '2018':59832}
luminosity = years[options.dataYear]


channel_mapping = {
    "all" : 'Ch2'
    }

#Hct_j4_h_DNN_b2_Ch2__TuneCP5up
channel = options.channel 
individual_discriminants = { # support regex (allow to avoid ambiguities if many histogram contains same patterns)
        'DNN': get_hist_regex('h_dnn_pred_S5'),
        }

discriminants = { # 'name of datacard' : list of tuple with (dicriminant ID, name in 'individual_discriminants' dictionary above). Make sure the 'name of datacard' ends with '_categoryName (for plot step)
    "DNN_st_lfv_cs" : [ (1, 'DNN')],
    "DNN_st_lfv_ct" : [ (1, 'DNN')],
    "DNN_st_lfv_cv" : [ (1, 'DNN')],
    "DNN_st_lfv_us" : [ (1, 'DNN')],
    "DNN_st_lfv_ut" : [ (1, 'DNN')],
    "DNN_st_lfv_uv" : [ (1, 'DNN')],
    #key does matter when removeing qcd-relavant discriminant below
    }

# IF you change Bkg Def, don't forget to change also the backgrounds list in main and the systematics for cross sections
# ~Kirill definition of Bkg
processes_mapping = { # Dict with { key(human friendly name of your choice) : value(regex to find rootfile) }. Be carefull not to match too many files with the regex!
                      # Data !Must! contain 'data_%channels' in the key and MC must not have data in the key
        # Background
        ## TT Semileptonic 
        ## Other Bkg
        #'wJets' : ['hist_WJetsToLNu_HT0To100.root', 'hist_WJetsToLNu_HT100To200.root', 'hist_WJetsToLNu_HT1200To2500.root', 'hist_WJetsToLNu_HT200To400.root', 'hist_WJetsToLNu_HT2500ToInf.root', 'hist_WJetsToLNu_HT400To600.root', 'hist_WJetsToLNu_HT600To800.root', 'hist_WJetsToLNu_HT800To1200.root'],
        'wJets' : [ 'hist_WJetsToLNu_HT1200To2500.root', 'hist_WJetsToLNu_HT200To400.root', 'hist_WJetsToLNu_HT2500ToInf.root', 'hist_WJetsToLNu_HT400To600.root', 'hist_WJetsToLNu_HT600To800.root', 'hist_WJetsToLNu_HT800To1200.root'],
        'vv' : ['hist_WW.root','hist_WZ.root','hist_ZZ.root'],
        'DY' : ['hist_DYJetsToLL_M50_amc.root','hist_DYJetsToLL_M-10to50.root'],
        'TTX' : ['hist_TTWJetsToLNu.root','hist_TTWJetsToQQ.root','hist_TTZToLLNuNu.root','hist_TTZToQQ.root','hist_ttHTobb.root','hist_ttHToNonbb.root'],
        #'ST_t-channel' : ['hist_ST_t_antitop_4f.root','hist_ST_t_top_4f.root'],
        #'ST_tW' : ['hist_ST_tW_antitop_5f.root','hist_ST_tW_top_5f.root'],
        'tt': ['hist_TTToSemiLeptonic.root','hist_TTTo2L2Nu.root'],
	'singleTop':['hist_ST_t_antitop_4f.root','hist_ST_t_top_4f.root','hist_ST_tW_antitop_5f.root','hist_ST_tW_top_5f.root'],
        'other' : [ 'hist_WJetsToLNu_HT1200To2500.root', 'hist_WJetsToLNu_HT200To400.root', 'hist_WJetsToLNu_HT2500ToInf.root', 'hist_WJetsToLNu_HT400To600.root', 'hist_WJetsToLNu_HT600To800.root', 'hist_WJetsToLNu_HT800To1200.root','hist_WW.root','hist_WZ.root','hist_ZZ.root','hist_TTWJetsToLNu.root','hist_TTWJetsToQQ.root','hist_TTZToLLNuNu.root','hist_TTZToQQ.root','hist_ttHTobb.root','hist_ttHToNonbb.root'],
        #'other' : ['hist_TTToHadronic.root', 'hist_WJetsToLNu_HT1200To2500.root', 'hist_WJetsToLNu_HT200To400.root', 'hist_WJetsToLNu_HT2500ToInf.root', 'hist_WJetsToLNu_HT400To600.root', 'hist_WJetsToLNu_HT600To800.root', 'hist_WJetsToLNu_HT800To1200.root','hist_WW.root','hist_WZ.root','hist_ZZ.root','hist_DYJetsToLL_M50_amc.root','hist_DYJetsToLL_M-10to50.root','hist_TTWJetsToLNu.root','hist_TTWJetsToQQ.root','hist_TTZToLLNuNu.root','hist_TTZToQQ.root','hist_ttHTobb.root','hist_ttHToNonbb.root'],
	# QCD
        #'qcd': ['hist_QCD_Pt1000_MuEnriched.root', 'hist_QCD_Pt120To170_MuEnriched.root', 'hist_QCD_Pt170To300_MuEnriched.root', 'hist_QCD_Pt20To30_MuEnriched.root', 'hist_QCD_Pt300To470_MuEnriched.root', 'hist_QCD_Pt30To50_MuEnriched.root', 'hist_QCD_Pt470To600_MuEnriched.root', 'hist_QCD_Pt50To80_MuEnriched.root', 'hist_QCD_Pt600To800_MuEnriched.root', 'hist_QCD_Pt800To1000_MuEnriched.root', 'hist_QCD_Pt80To120_MuEnriched.root'],
        # Signal
        'st_lfv_cs': ['hist_ST_LFV_TCMuTau_Scalar.root','hist_TT_LFV_TCMuTau_Scalar.root'],
        'st_lfv_ct': ['hist_ST_LFV_TCMuTau_Tensor.root','hist_TT_LFV_TCMuTau_Tensor.root'],
        'st_lfv_cv': ['hist_ST_LFV_TCMuTau_Vector.root','hist_TT_LFV_TCMuTau_Vector.root'],
        'st_lfv_us': ['hist_ST_LFV_TUMuTau_Scalar.root','hist_TT_LFV_TUMuTau_Scalar.root'],
        'st_lfv_ut': ['hist_ST_LFV_TUMuTau_Tensor.root','hist_TT_LFV_TUMuTau_Tensor.root'],
        'st_lfv_uv': ['hist_ST_LFV_TUMuTau_Vector.root','hist_TT_LFV_TUMuTau_Vector.root'],
        # Data
        'data_all' : ['hist_SingleMuon'+options.dataYear+'.root'],
        }

processes_mapping['data_obs'] = processes_mapping['data_all']
processes_mapping.pop('data_all')


smTTlist = ['tt'] # for systematics affecting only SM tt
lfvlist = ['st_lfv_cs','st_lfv_ct','st_lfv_cv','st_lfv_uv','st_lfv_ut','st_lfv_us'] 

if options.applyxsec:
    # Read Xsec file
    with open(options.xsecfile, 'r') as xsec_file:
        xsec_data = yaml.load(xsec_file)
    if not xsec_data:
        print("Error loading the cross section file %s"%options.xsecfile)
        sys.exit(1)
    
def main():
    """Main function"""
    signals = ['st_lfv_cs','st_lfv_ct','st_lfv_cv','st_lfv_uv','st_lfv_ut','st_lfv_us']
    #signals = ['st_lfv_cs']
    backgrounds = ['tt', 'other' , 'singleTop', 'wJets','vv','DY','TTX'] #,'singleTop'] #, 'qcd']

    #print("Background considered: ", backgrounds)

    for signal in signals:
	for key, value in discriminants.iteritems():
		print(key, value)
        dicriminants_per_signal = dict((key,value) for key, value in discriminants.iteritems() if signal in key)
	#print("dicriminants_per_signal : ", dicriminants_per_signal)
        for discriminant in dicriminants_per_signal.keys() :
            #print("signal :" , signal , "discrimanant :", discriminant)
            prepareShapes(backgrounds, [signal], dicriminants_per_signal[discriminant], discriminant)

def merge_histograms(process, histogram, destination):
    """
    Merge two histograms together. If the destination histogram does not exist, it
    is created by cloning the input histogram

    Parameters:

    process         Name of the current process
    histogram       Pointer to TH1 to merge
    destination     Dict of destination histograms. The key is the current category.

    Return:
    The merged histogram
    """

    if not histogram:
        raise Exception('Missing histogram for %r. This should not happen.' % process)

    #if histogram.GetEntries() == 0:
    #    return

    # Rescale histogram to luminosity, if it's not data
    if not 'data' in process:
        #print("HISTOGRAMS are being Lumi scaled")
        #print("HIST TITLE : " , histogram.GetName())
        histogram.Scale(luminosity)
    import array
    arr = array.array('d',[0,1,2,5,10,30,60])
    histogram = histogram.Rebin(len(arr)-1, histogram.GetName(), arr)

    d = destination
    if not d:
        d = histogram.Clone()
        d.SetDirectory(ROOT.nullptr)
    else:
        d.Add(histogram)
    setNegativeBinsToZero(d, process)

    return d


def prepareFile(processes_map, categories_map, root_path, discriminant):
    """
    Prepare a ROOT file suitable for Combine Harvester.

    The structure is the following:
      1) Each observable is mapped to a subfolder. The name of the folder is the name of the observable
      2) Inside each folder, there's a bunch of histogram, one per background and signal hypothesis. The name of the histogram is the name of the background.
    """

    import re

    print("Preparing ROOT file for %s..."%discriminant)

    output_filename = os.path.join(options.output, 'shapes_%s.root' % (discriminant))
    if not os.path.exists(os.path.dirname(output_filename)):
        os.makedirs(os.path.dirname(output_filename))

    files = [os.path.join(root_path, f) for f in os.listdir(root_path) if f.endswith('.root')]

    # Gather a list of inputs files for each process.
    # The key is the process identifier, the value is a list of files
    # If more than one file exist for a given process, the histograms of each file will
    # be merged together later
    processes_files = {}
    for process, paths in processes_map.items():
        process_files = []
        for path in paths:
            r = re.compile(path, re.IGNORECASE)
            process_files += [f for f in files if r.search(f)]
        if len(process_files) == 0:
          print('Warning: no file found for %s'%process)
        processes_files[process] = process_files
        print("Files found for %s: "%(process), [os.path.basename(filename) for filename in process_files])

    # Create the list of histograms (nominal + systematics) for each category
    # we are interested in.
    # The key is the category name, and the value is a list of histogram. The list will always
    # contain at least one histogram (the nominal histogram), and possibly more, two per systematic (up & down variation)
    histogram_names = {}
    for discriminant_tuple in categories_map[discriminant]:
        discriminant_name = discriminant_tuple[1]
        #print("**** discriminant_name : " , discriminant_name )
        r = re.compile(individual_discriminants[discriminant_name], re.IGNORECASE)
        #f = ROOT.TFile.Open(processes_files.values()[0][0])
        f = ROOT.TFile.Open(processes_files['tt'][0])
        #print("processes_files keys : " , processes_files['tt'])
        histogram_names[discriminant_name] = [n.GetName() for n in f.GetListOfKeys() if r.search(n.GetName())]
        f.Close()


    # Extract list of systematics from the list of histograms derived above
    # This code assumes that *all* categories contains the same systematics (as it should)
    # The systematics list is extracted from the histogram list of the first category
    # The list of expanded histogram name is also extract (ie, regex -> full histogram name)
    #print("HIST NAMES : " , histogram_names)
    systematics = set()
    histograms = {}
    systematics_regex = re.compile('__(.*)(up|down)$', re.IGNORECASE)
    #print("Histogram names :", histogram_names)
    for category, histogram_names in histogram_names.items():
        for histogram_name in histogram_names:
            #print("Histogram name :" , histogram_name)
            m = systematics_regex.search(histogram_name)
            if m:
                # It's a systematic histogram
                systematics.add(m.group(1))
            else:
                nominal_name = histogram_name
                if category in histograms:
                    # Check that the regex used by the user only match 1 histogram
                    if histograms[category] != nominal_name:
                        raise Exception("The regular expression used for category %r matches more than one histogram: %r and %r" % (category, nominal_name, histograms[category]))
                histograms[category] = nominal_name
    print("Found the following systematics in rootfiles: ", systematics)
    if options.sysToAvoid:
	#print("***" , options.sysToAvoid)
        for sysToAvoid in options.sysToAvoid:
            systematics.remove(sysToAvoid)
        #print("After ignoring the one mentioned with sysToAvoid option: ", systematics)

    cms_systematics = [CMSNamingConvention(s,options) for s in systematics]

    def dict_get(dict, name):
        if name in dict:
            return dict[name]
        else:
            return None

    # Create final shapes
    shapes = {}
    for category, original_histogram_name in histograms.items():
        shapes[category] = {}
        for process, process_files in processes_files.items():
            shapes[category][process] = {}

            for process_file in process_files:
                f = ROOT.TFile.Open(process_file)
                TH1 = f.Get(original_histogram_name)
		#print("ORIGINAL : ", original_histogram_name)
                process_file_basename = os.path.basename(process_file)
                if not TH1:
                    #print "No histo named %s in %s. ORIGINAL Exitting..."%(original_histogram_name, process_file)

                    sys.exit()  ##UNCOMMETNT ECEEEE
                if options.applyxsec and not 'data' in process:
                    xsec = xsec_data[process_file_basename]['cross-section']
                    nevt = xsec_data[process_file_basename]['generated-events']
                    #print("Applying cross sec and nevt on %s "%process_file_basename, xsec, " ", nevt)
		    #print("Nominal Integral Before scale : " , TH1.Integral())
                    TH1.Scale(xsec/float(nevt)) #ECEEEE
		    #print("Nominal Integral After scale : " , TH1.Integral())
                shapes[category][process]['nominal'] = merge_histograms(process, TH1, dict_get(shapes[category][process], 'nominal'))
                if not "data" in process: 
                    for systematic in systematics:
			#print("SYSTEMATIIC : " , systematic)
			#Accidently count pdfalphas in the rest pdf list 
			#if "pdf51" in systematic: continue  
                        if systematic in [item for item in sysForSMtt if item not in sysForSig] \
                            and not process in smTTlist: continue
                        if systematic in sysForSMtt and not process in lfvlist+smTTlist: continue
                        for variation in ['up', 'down']:
                            key = CMSNamingConvention(systematic,options) + variation.capitalize()
                            TH1_syst = f.Get(original_histogram_name + '__' + systematic + variation)
                            if not TH1_syst:
                                #print "YES YES here ... No histo named %s in %s in %s"%(original_histogram_name + '__' +  systematic + variation, process_file_basename, process)
                                sys.exit()
                            if options.applyxsec and not 'data' in process and TH1_syst:
				#print("systematic : ", systematic , "Inetgral : " , TH1_syst.Integral())
                                TH1_syst.Scale(xsec/float(nevt)) #REMOVE IF ECEEEE
				#print("systematic : ", systematic , "Inetgral After scale : " , TH1_syst.Integral())
                            #print("SYSTEMTIC to be scaled with LUMI: " , systematic)
                            shapes[category][process][key] = merge_histograms(process, TH1_syst, dict_get(shapes[category][process], key))
                f.Close()
    #print("Shapes :  ", shapes["DNN"]["TTX"].keys())
    output_file = ROOT.TFile.Open(output_filename, 'recreate')
    #print("Writing file here: " , output_filename)
    for category, processes in shapes.items():
        #print("For category : " , category , "Process : ", processes)
        output_file.mkdir(category).cd()
        for process, systematics_ in processes.items():
            for systematic, histogram in systematics_.items():
                #print("Writing histograms ... ")
                histogram.SetName(process if systematic == 'nominal' else process + '__' + systematic)
                histogram.Write()
        output_file.cd()

    output_file.Close()
    print("Done. File saved as %r" % output_filename)

    return output_filename, cms_systematics

def prepareShapes(backgrounds, signals, discriminant, discriminantName):
    # Backgrounds is a list of string of the considered backgrounds corresponding to entries in processes_mapping 
    # Signals is a list of string of the considered signals corresponding to entries in processes_mapping 
    # discriminant is the corresponding entry in the dictionary discriminants 

    import CombineHarvester.CombineTools.ch as ch
    root_path = options.root_path

    file, systematics = prepareFile(processes_mapping, discriminants, root_path, discriminantName)
    call(['python', 'symmetrize.py', options.output, file, options.dataYear], shell=False)
    
    for signal in signals :
	print("Before combine harvester :",signal)
        cb = ch.CombineHarvester()
        cb.AddObservations(['*'], [''], ['_%s'%options.dataYear], [''], discriminant)
        cb.AddProcesses(['*'], [''], ['_%s'%options.dataYear], [''], [signal], discriminant, True)
        cb.AddProcesses(['*'], [''], ['_%s'%options.dataYear], [''], backgrounds, discriminant, False)

        # Systematics
        if not options.nosys:
            #print("systematics just before datacards : " , systematics)
            for systematic in systematics:
                systematic_only_for_SMtt = False
                systematic_only_for_Sig = False

                for systSMtt in sysForSMtt:
                    if CMSNamingConvention(systSMtt,options) == systematic:
                        systematic_only_for_SMtt = True
                for systSig in sysForSig:
                    if CMSNamingConvention(systSig,options) == systematic:
                        systematic_only_for_Sig = True
		#print("signal :", signal ,"systematic_only_for_Sig :", systematic_only_for_Sig )
		#print("systematic_only_for_SMtt :", systematic_only_for_SMtt )
                if not systematic_only_for_SMtt and not systematic_only_for_Sig:
                    #print("No tt , no signal")
                    cb.cp().AddSyst(cb, systematic, 'shape', ch.SystMap()(1.00))
                elif systematic_only_for_SMtt and not systematic_only_for_Sig:
                    cb.cp().AddSyst(cb, systematic, 'shape', ch.SystMap('process')(smTTlist, 1.00))
                elif not systematic_only_for_SMtt and systematic_only_for_Sig:
                    cb.cp().AddSyst(cb, systematic, 'shape', ch.SystMap('process')([signal], 1.00))
                else:
                    cb.cp().AddSyst(cb, systematic, 'shape', ch.SystMap('process')(smTTlist+[signal], 1.00))
		    #print("I am adding " ,systematic , "to process ", smTTlist+[signal] )

            #Lumi corr. https://twiki.cern.ch/twiki/bin/view/CMS/TWikiLUM#LumiComb
            #cb.cp().AddSyst(cb, 'CMS_lumi', 'lnN', ch.SystMap()(options.luminosityError))

            if '2016' in options.dataYear:
                cb.cp().AddSyst(cb, 'CMS_lumi_uncorr_2016', 'lnN', ch.SystMap()(1.01))
                cb.cp().AddSyst(cb, 'CMS_lumi_corr_161718', 'lnN', ch.SystMap()(1.006))
                #reproducing 2016
                #cb.cp().AddSyst(cb, 'CMS_lumi_uncorr_2016', 'lnN', ch.SystMap()(1.027))
            elif options.dataYear == '2017':
                cb.cp().AddSyst(cb, 'CMS_lumi_uncorr_2017', 'lnN', ch.SystMap()(1.02))
                cb.cp().AddSyst(cb, 'CMS_lumi_corr_161718', 'lnN', ch.SystMap()(1.009))
                cb.cp().AddSyst(cb, 'CMS_lumi_corr_1718', 'lnN', ch.SystMap()(1.006))
            elif options.dataYear == '2018':
                cb.cp().AddSyst(cb, 'CMS_lumi_uncorr_2018', 'lnN', ch.SystMap()(1.015))
                cb.cp().AddSyst(cb, 'CMS_lumi_corr_161718', 'lnN', ch.SystMap()(1.02))
                cb.cp().AddSyst(cb, 'CMS_lumi_corr_1718', 'lnN', ch.SystMap()(1.002))

            #cb.cp().AddSyst(cb, 'trigger_eff', 'lnN', ch.SystMap()(1.02))
            cb.cp().AddSyst(cb, 'xsec_tt', 'lnN', ch.SystMap('process')(['tt'], 1.044))
            cb.cp().AddSyst(cb, 'xsec_ttX', 'lnN', ch.SystMap('process')(['TTX'], 1.2))
            cb.cp().AddSyst(cb, 'xsec_vv', 'lnN', ch.SystMap('process')(['vv'], 1.1))
            cb.cp().AddSyst(cb, 'xsec_dy', 'lnN', ch.SystMap('process')(['DY'], 1.1))
            cb.cp().AddSyst(cb, 'xsec_wjets', 'lnN', ch.SystMap('process')(['wJets'], 1.1))
            cb.cp().AddSyst(cb, 'xsec_singleTop', 'lnN', ch.SystMap('process')(['singleTop'], 1.1))
            cb.cp().AddSyst(cb, 'xsec_Other', 'lnN', ch.SystMap('process')(['other'], 1.1))
            #cb.cp().AddSyst(cb, 'hdamp', 'lnN', ch.SystMap('process')(smTTlist, 1.05))
            #cb.cp().AddSyst(cb, 'TuneCP5', 'lnN', ch.SystMap('process')(smTTlist, 1.03))

            #print("All good so far")
        # Import shapes from ROOT file
        cb.cp().backgrounds().ExtractShapes(file, '$BIN/$PROCESS', '$BIN/$PROCESS__$SYSTEMATIC')
	print("OK got the background")
        cb.cp().signals().ExtractShapes(file, '$BIN/$PROCESS', '$BIN/$PROCESS__$SYSTEMATIC')
	print("OK got the signals")


        #AutoMCStat
        cb.SetAutoMCStats(cb, 0.1)

        output_prefix = 'TOP_LFV_%s_Discriminant_%s' % (signal, discriminantName)

        output_dir = os.path.join(options.output, '%s' % (signal))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        fake_mass = '125'

        # Write card
        datacard = os.path.join(output_dir, output_prefix + '.dat')
        cb.cp().mass([fake_mass, "*"]).WriteDatacard(os.path.join(output_dir, output_prefix + '.dat'), os.path.join(output_dir, output_prefix + '_shapes.root'))

        # Write small script to compute the limit
        workspace_file = os.path.basename(os.path.join(output_dir, output_prefix + '_combine_workspace.root'))
        script = """#! /bin/bash

text2workspace.py {datacard} -m {fake_mass} -o {workspace_root}

# Run limit

echo combine -M AsymptoticLimits -n {name} {workspace_root} --run blind #-v +2
combine -M AsymptoticLimits -n {name} {workspace_root} --run blind --rMin -1 --rMax 1 --rAbsAcc 0.0000005 --expectSignal 1 --cminDefaultMinimizerStrategy 0 #-v +2
#combine -H AsymptoticLimits -M HybridNew -n {name} {workspace_root} --LHCmode LHC-limits --expectedFromGrid 0.5 #for ecpected, use 0.84 and 0.16
""".format(workspace_root=workspace_file, datacard=os.path.basename(datacard), name=output_prefix, fake_mass=fake_mass, systematics=(0 if options.nosys else 1))
        script_file = os.path.join(output_dir, output_prefix + '_run_limits.sh')
        with open(script_file, 'w') as f:
            f.write(script)
        
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)


        # Write small script for datacard checks
        script = """#! /bin/bash

# Run checks
echo combine -M FitDiagnostics -t -1 --expectSignal 0 {datacard} -n fitDiagnostics_{name}_bkgOnly -m 125 --robustHesse 1 --robustFit=1 --rMin -20 --rMax 20 #--plots
echo python ../../../../HiggsAnalysis/CombinedLimit/test/diffNuisances.py -a fitDiagnostics_{name}_bkgOnly.root -g fitDiagnostics_{name}_bkgOnly_plots.root
combine -M FitDiagnostics -t -1 --expectSignal 0 {datacard} -n _{name}_bkgOnly -m 125 --robustHesse 1 --robustFit=1 --rMin -20 --rMax 20 #--plots
python ../../../../HiggsAnalysis/CombinedLimit/test/diffNuisances.py -a fitDiagnostics_{name}_bkgOnly.root -g fitDiagnostics_{name}_bkgOnly_plots.root --skipFitS > fitDiagnostics_{name}_bkgOnly.log
python ../../printPulls.py fitDiagnostics_{name}_bkgOnly_plots.root
combine -M FitDiagnostics -t -1 --expectSignal 1 {datacard} -n _{name}_bkgPlusSig -m 125 --robustHesse 1 --robustFit=1 --rMin -20 --rMax 20 #--plots
python ../../../../HiggsAnalysis/CombinedLimit/test/diffNuisances.py -a fitDiagnostics_{name}_bkgPlusSig.root -g fitDiagnostics_{name}_bkgPlusSig_plots.root --skipFitB > fitDiagnostics_{name}_bkgPlusSig.log
python ../../printPulls.py fitDiagnostics_{name}_bkgPlusSig_plots.root

#print NLL for check
combineTool.py -M FastScan -w {name}_combine_workspace.root:w -o {name}_nll
""".format(workspace_root=workspace_file, datacard=os.path.basename(datacard), name=output_prefix, fake_mass=fake_mass, systematics=(0 if options.nosys else 1))
        script_file = os.path.join(output_dir, output_prefix + '_run_closureChecks.sh')
        with open(script_file, 'w') as f:
            f.write(script)
        
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

        # Write small script for impacts
        script = """#! /bin/bash

# Run impacts
combineTool.py -M Impacts -d {name}_combine_workspace.root -m 125 --doInitialFit --robustFit=1 --robustHesse 1 --rMin -20 --rMax 20 -t -1
combineTool.py -M Impacts -d {name}_combine_workspace.root -m 125 --robustFit=1 --robustHesse 1 --doFits --rMin -20 --rMax 20 -t -1 --parallel 50
combineTool.py -M Impacts -d {name}_combine_workspace.root -m 125 -o {name}_expected_impacts.json --rMin -20 --rMax 20 -t -1
plotImpacts.py -i {name}_expected_impacts.json -o {name}_expected_impacts --per-page 50

#combineTool.py -M Impacts -d {name}_combine_workspace.root -m 125 --doInitialFit --robustFit=1 --robustHesse 1 --rMin -20 --rMax 20
#combineTool.py -M Impacts -d {name}_combine_workspace.root -m 125 --robustFit=1 --doFits --robustHesse 1 --rMin -20 --rMax 20 --parallel 32
#combineTool.py -M Impacts -d {name}_combine_workspace.root -m 125 -o {name}_impacts.json --rMin -20 --rMax 20
#plotImpacts.py -i {name}_impacts.json -o {name}_impacts --per-page 50
""".format(workspace_root=workspace_file, datacard=os.path.basename(datacard), name=output_prefix, fake_mass=fake_mass, systematics=(0 if options.nosys else 1))
        script_file = os.path.join(output_dir, output_prefix + '_run_impacts.sh')
        with open(script_file, 'w') as f:
            f.write(script)
        
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

        # Write small script for postfit shapes
        script = """#! /bin/bash

# Run postfit
echo combine -M FitDiagnostics {datacard} -n _{name}_postfit --saveNormalizations --saveShapes --saveWithUncertainties --preFitValue 0 --rMin -20 --rMax 20 --robustHesse 1 --robustFit=1 -v 1
combine -M FitDiagnostics {datacard} -n _{name}_postfit --saveNormalizations --saveShapes --saveWithUncertainties --preFitValue 0 --rMin -20 --rMax 20 --robustHesse 1 --robustFit=1 -v 1 #--plots
PostFitShapesFromWorkspace -w {name}_combine_workspace.root -d {datacard} -o postfit_shapes_{name}.root -f fitDiagnostics_{name}_postfit.root:fit_b --postfit --sampling
python ../../convertPostfitShapesForPlotIt.py -i postfit_shapes_{name}.root
$CMSSW_BASE/src/UserCode/HEPToolsFCNC/plotIt/plotIt -o postfit_shapes_{name}_forPlotIt ../../postfit_plotIt_config_{coupling}_{year}.yml -y
$CMSSW_BASE/src/UserCode/HEPToolsFCNC/plotIt/plotIt -o postfit_shapes_{name}_forPlotIt ../../postfit_plotIt_config_{coupling}_{year}_qcd.yml -y
""".format(workspace_root=workspace_file, datacard=os.path.basename(datacard), name=output_prefix, fake_mass=fake_mass, systematics=(0 if options.nosys else 1), coupling=("st_lfv"), year=options.dataYear)
        script_file = os.path.join(output_dir, output_prefix + '_run_postfit.sh')
        with open(script_file, 'w') as f:
            f.write(script)
        
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

def CMSNamingConvention(syst,options):
    # Taken from https://twiki.cern.ch/twiki/bin/view/CMS/HiggsWG/HiggsCombinationConventions
    # systlist = ['jes', 'jer', 'elidiso', 'muidiso', 'jjbtag', 'pu', 'trigeff']
    #if syst not in options.correlatedSys:
    syst_year = options.dataYear
    if '2016' in options.dataYear: syst_year = "2016"
    if syst not in correlatedSys:
        return 'CMS_' + syst_year + '_' + syst
    else:
        return 'CMS_' + syst

if __name__ == '__main__':
    main()

