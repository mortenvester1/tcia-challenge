import os
import sys
import pdb
import time
import uuid

import dicom
import dicom_numpy
import scipy as sp
import numpy as np
import pandas as pd

import nibabel as nib

import SimpleITK as sitk
from scipy import ndimage as nd
from sklearn.feature_extraction import image

dir_path = os.path.dirname(os.path.realpath(__file__))
train_dir = dir_path.rstrip("src") + "traindata"
test_dir = dir_path.rstrip("src") + "testdata"

def register_patient(df, data_dir, data_type = "Train"):
    dir_path = "/Users/vester/Desktop/"
    for pid in df.ProxID.unique():

        temp = df.loc[df.ProxID == pid]
        try:
            # Get ADC, BVAL Dirs
            names = temp.Name.values
            adc_dir = temp[[name.endswith("ADC0") for name in names]].DCMSerUID.unique()[0]
            bval_dir = temp[[name.endswith("BVAL0") for name in names]].DCMSerUID.unique()[0]
            dicom_find = list(temp[[name.endswith("BVAL0") for name in names]].ijk.unique())
            dicom_find = [[int(coord) for coord in f.split(" ")] for f in dicom_find]


            adc_scale = temp[[name.endswith("ADC0") for name in names]].VoxelSpacing.unique()[0]
            bval_scale = temp[[name.endswith("BVAL0") for name in names]].VoxelSpacing.unique()[0]
            adc_wm = temp[[name.endswith("ADC0") for name in names]].WorldMatrix.unique()[0]
            bval_wm = temp[[name.endswith("BVAL0") for name in names]].WorldMatrix.unique()[0]
            adc_wm = np.array(adc_wm.split(","), np.float).reshape(4,4)
            bval_wm = np.array(bval_wm.split(","), np.float).reshape(4,4)

        except:
            continue

        dicom_path = data_dir + "/".join(["/raw/dicom", pid])
        ktrans_path = data_dir + "/".join(["/raw/ktrans", pid, pid])

        # Get Images
        imga = load_dicom(dicom_path, adc_dir)
        imgb = load_dicom(dicom_path, bval_dir)
        imgk = load_ktrans(ktrans_path)

        # Get Scale and set scale, since it is weird
        imga['scale'] = np.array(adc_scale[::-1].split(','), dtype = np.float)
        imgb['scale'] = np.array(bval_scale[::-1].split(','), dtype = np.float)
        imga['img'].SetSpacing(imga['scale'][::-1])
        imgb['img'].SetSpacing(imgb['scale'][::-1])

        #reg_input = get_registration_dicts(imga['img'], imgb['img'], imgk['img'], fixed = 'adc')

        #
        reg_input = get_registration_dicts(sitk.GetImageFromArray(rescale_arr(imga['arr'],imga['scale'])),
                                           sitk.GetImageFromArray(rescale_arr(imgb['arr'],imgb['scale'])),
                                           sitk.GetImageFromArray(rescale_arr(imgk['arr'],imgk['scale'])),
                                           fixed = 'adc')
        # Registration
        resampled = register_images(fixed_img = reg_input[0], moving_imgs = reg_input[1:])
        pdb.set_trace()
        sitk.WriteImage(original_image, output_file_name_3D)
        # Saving Nifti For viewing
        save_nifti(dir_path + "raw", imga['arr'], imgb['arr'], imgk['arr'])
        dicts_2_nifti(dir_path + "resampled", resampled)

        # Trying resizing
        tra = sitk.ScaleTransform(3, 1./imga['scale'])
        trb = sitk.ScaleTransform(3, 1./imga['scale'])
        trc = sitk.ScaleTransform(3, 1./imga['scale'])
        timg = resample(imgk['img'], transform)
        tarr = sitk.GetArrayFromImage(timg)
        affine = np.diag([1, 1, 1, 1])
        tnib = nib.Nifti1Image(tarr, affine)
        nib.save(tnib, dir_path+'test.nii')

        tarr = rescale_arr(imgk['arr'], imgk['scale'])
        affine = np.diag([1, 1, 1, 1])
        tnib = nib.Nifti1Image(tarr, affine)
        nib.save(tnib, dir_path+'atest.nii')

        pdb.set_trace()

    return


def get_mhd(path):
    """
    read mhd files
    """
    with open(path) as mhd:
        header = mhd.read()
        header = [h.split(" = ") for h in header.split("\n")]
        header = dict(header[:-1])

    if 'TransformMatrix' in header:
        header['TransformMatrix'] = np.array(header['TransformMatrix'].split(" "), dtype=np.float)
    if 'Offset' in header:
        header['Offset'] = np.array(header['Offset'].split(" "), dtype=np.float)
    if 'ElementSpacing' in header:
        header['ElementSpacing'] = np.array(header['ElementSpacing'].split(" "), dtype=np.float)
    if 'NDims' in header:
        header['NDims'] = int(header['NDims'])
    if 'DimSize' in header:
        header['DimSize'] = np.array(header['DimSize'].split(" "), dtype=np.int)
    if 'CenterOfRotation' in header:
        header['CenterOfRotation'] = np.array(header['CenterOfRotation'].split(" "), dtype=np.int)

    return header


def save_nifti(dir_path, adc, bval, ktrans):
    affine = np.diag([1, 1, 1, 1])
    adc_img = nib.Nifti1Image(adc, affine)
    bval_img = nib.Nifti1Image(bval, affine)
    ktrans_img = nib.Nifti1Image(ktrans, affine)

    nib.save(adc_img, dir_path+'adc.nii')
    nib.save(bval_img, dir_path+'bval.nii')
    nib.save(ktrans_img, dir_path+'ktrans.nii')
    return


def load_ktrans(path):
    """
    # z,y,x
    """
    ext = "-Ktrans.mhd"
    img = sitk.ReadImage(path + ext)
    data = extract_info_from_sitk_img(img)

    return data


def load_dicom(path, dicom_dir):
    subdir = os.listdir(path)[-1]
    dicom_dir = "/".join([path, subdir, dicom_dir])

    files = []
    for f in os.listdir(dicom_dir):
        if not f.endswith("dcm"):
            continue
        filepath = dicom_dir + "/" + f
        files.append(filepath)

    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(files)
    img = reader.Execute()
    data = extract_info_from_sitk_img(img)

    return data


def extract_info_from_sitk_img(img):
    arr = sitk.GetArrayFromImage(img)
    origin = np.array(list(reversed(img.GetOrigin())), dtype = np.float)
    scale = np.array(list(reversed(img.GetSpacing())), dtype = np.float)
    direction = np.array(list(img.GetDirection()), dtype = np.float)

    arr = normalize_arr(arr, 'std')
    data = {
        "img" : img,
        "arr" : arr,
        "origin" : origin,
        "scale" : scale,
        "direction" : direction
    }

    return data


def normalize_arr(arr, norm_type = "std"):
    if norm_type == "minmax":
        arr_min = float(arr.min())
        arr_max = float(arr.max())
        arr_min_max = (arr - arr_min)/(arr_max - arr_min)
        return arr_min_max
    else:
        arr = np.divide(arr,arr.sum())
    return arr


def resample(image, transform):
    # Output image Origin, Spacing, Size, Direction are taken from the reference
    # image in this call to Resample
    reference_image = sitk.Image(400, 400, 200, sitk.sitkFloat32)
    reference_image.SetOrigin(image.GetOrigin())
    reference_image.SetSpacing(image.GetSpacing())
    reference_image.SetDirection(image.GetDirection())

    interpolator = sitk.sitkBSpline
    default_value = 0
    new_img = sitk.Resample(image,
                            reference_image,
                            transform,
                            interpolator,
                            default_value)
    return new_img


def rescaled_img_from_arr(img, arr, scale, direction, origin):
    rescaled_arr = rescaled_arr(arr, scale)
    rescaled_img = None
    return rescaled_img, rescaled_arr


def rescale_arr(arr, scale):
    arr = nd.interpolation.zoom(arr.astype(np.float), zoom = scale, order = 1)
    arr /= arr.sum()
    arr[np.abs(arr) < 1e-16] = 0
    return arr


def register_images(fixed_img, moving_imgs):
    """
    See https://goo.gl/kF2x9Z
    """

    fixed = sitk.Cast(fixed_img['img'], sitk.sitkFloat32)

    resampled = []
    for moving_img in moving_imgs:
        moving = sitk.Cast(moving_img['img'],sitk.sitkFloat32)
        # Align Images
        moving, init_transform = align_images(fixed, moving)
        # Registration
        moving = register_image(fixed, moving, init_transform)

        resampled.append(moving)

    results = get_registration_dicts(fixed, *resampled, fixed = fixed_img['name'])
    return results


def align_images(fixed, moving):
    """
    Initial Alignment of two images
    """
    init_transform = sitk.CenteredTransformInitializer(\
                            fixed,
                            moving,
                            sitk.Euler3DTransform(),
                            sitk.CenteredTransformInitializerFilter.GEOMETRY)

    moving_resampled = sitk.Resample(\
                            moving,
                            fixed,
                            init_transform,
                            sitk.sitkLinear,
                            0.0,
                            moving.GetPixelID())

    return moving, init_transform


def register_image(fixed, moving, initial_transform):
    arr = sitk.GetArrayFromImage(moving)
    registration_method = sitk.ImageRegistrationMethod()

    # Similarity metric settings.
    registration_method.SetMetricAsMattesMutualInformation(numberOfHistogramBins=100)
    registration_method.SetMetricSamplingStrategy(registration_method.RANDOM)
    registration_method.SetMetricSamplingPercentage(0.1)
    registration_method.SetInterpolator(sitk.sitkBSpline)

    # Optimizer settings.
    registration_method.SetOptimizerAsGradientDescent(learningRate=0.01, numberOfIterations=100, convergenceMinimumValue=1e-6, convergenceWindowSize=10)
    #registration_method.SetOptimizerScalesFromPhysicalShift()

    # Setup for the multi-resolution framework.
    #registration_method.SetShrinkFactorsPerLevel(shrinkFactors = [4,2,1])
    #registration_method.SetSmoothingSigmasPerLevel(smoothingSigmas=[2,1,0])
    #registration_method.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()

    # Don't optimize in-place, we would possibly like to run this cell multiple times.
    registration_method.SetInitialTransform(initial_transform, inPlace=False)
    registration_method.AddCommand(sitk.sitkStartEvent, lambda: print("Starting Registration"))
    registration_method.AddCommand(sitk.sitkProgressEvent, lambda: print("\rProgress: {0:03.1f}%...".format(100*registration_method.GetProgress()),end=''))
    registration_method.AddCommand(sitk.sitkProgressEvent, lambda: sys.stdout.flush())
    registration_method.AddCommand(sitk.sitkEndEvent, lambda: print("Registration Done"))
    # Connect all of the observers so that we can perform plotting during registration.
    #registration_method.AddCommand(sitk.sitkStartEvent, start_plot)
    #registration_method.AddCommand(sitk.sitkEndEvent, end_plot)
    #registration_method.AddCommand(sitk.sitkMultiResolutionIterationEvent, update_multires_iterations)
    #registration_method.AddCommand(sitk.sitkIterationEvent, lambda: plot_values(registration_method))

    final_transform = registration_method.Execute(fixed, moving)
    val = np.abs(arr).sum()
    arr -= sitk.GetArrayFromImage(moving)
    val2 = np.abs(arr).sum()
    print(val, val2)

    return moving


def get_registration_dicts(adc, bval, ktrans, fixed = 'adc'):
    dicts = [{ "name" : "adc", "img" : adc },
             { "name" : "bval", "img" : bval },
             { "name" : "ktrans", "img" : ktrans }]

    if fixed == "adc":
        return dicts
    elif fixed == "bval":
        return dicts[1,0,2]
    elif fixed == "ktrans":
        return dicts[2,1,0]
    else:
        return []


def dicts_2_nifti(dir_path, dicts):
    new_dict = dict([(d['name'], sitk.GetArrayFromImage(d['img'])) for d in dicts])
    save_nifti(dir_path, **new_dict)
    return


def transform_img(img, arr, scale, direction, origin):
    # Get Number of Dimensions
    dimension = len(scale)
    affine = sitk.AffineTransform(dimension)

    # Set Translation
    affine.SetTranslation(origin)

    # Set rotation
    affine.SetMatrix(direction)

    # Set Scaling Transform
    transform = sitk.ScaleTransform(dimension, 1./scale)

    # Resample
    img = resample(img, transform)

    return img


if __name__ == '__main__':
    df_train = pd.read_csv(train_dir + "/ProstateX2-DataInfo-Train/ProstateX-2-Images-Train.csv")
    df_test = pd.read_csv(test_dir + "/ProstateX2-DataInfo-Test/ProstateX-2-Images-Test.csv")

    register_patient(df_train, train_dir, data_type = "Train")
    register_patient(df_test, test_dir, data_type = "Test")
