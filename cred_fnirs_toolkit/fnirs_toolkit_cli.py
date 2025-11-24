#!/usr/bin/env python3
"""
fNIRS Toolkit CLI - Process SNIRF files and generate hemoglobin analysis reports
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import mne
import mne_nirs
import numpy as np
import pandas as pd
import seaborn as sns


def extract_trial_name(snirf_file: str) -> str:
    """Extract trial name from SNIRF filename (format: YYYYMMDD_TREATMENT_ID.snirf)"""
    filename = os.path.basename(snirf_file)
    filename_parts = filename.replace('.snirf', '').split('_')
    
    if len(filename_parts) >= 3:
        return f"{filename_parts[1]}_{filename_parts[2]}"  # treatment_participantID
    return filename.replace('.snirf', '')


def raw_intensity_to_hemo(snirf_file: str) -> Tuple[mne.io.Raw, str]:
    """
    Process a single SNIRF file through the complete pipeline to hemoglobin data
    
    Parameters:
    -----------
    snirf_file : str
        Path to SNIRF file
        
    Returns:
    --------
    tuple : (raw_hemo, trial_name)
        Processed hemoglobin data and trial identifier
    """
    trial_name = extract_trial_name(snirf_file)
    print(f"Loading data from: {os.path.basename(snirf_file)} (Trial: {trial_name})")
    
    # Load raw intensity data
    raw_intensity = mne.io.read_raw_snirf(snirf_file, optode_frame='unknown', verbose=False)
    raw_intensity.load_data()

    # Resample to 5 Hz
    print(f"  Data shape: {raw_intensity.get_data().shape}")
    print(f"  Sampling frequency: {raw_intensity.info['sfreq']} Hz")
    raw_intensity.resample(5)
    
    # Convert to hemoglobin concentration changes
    raw_od = mne.preprocessing.nirs.optical_density(raw_intensity, verbose=False)
    raw_od_corrected = mne.preprocessing.nirs.temporal_derivative_distribution_repair(raw_od, verbose=False)
    raw_od_filtered = raw_od_corrected.copy().filter(0.01, 0.25, method='fir', fir_design='firwin', verbose=False)
    raw_hemo = mne.preprocessing.nirs.beer_lambert_law(raw_od_filtered, ppf=0.1)
    
    return raw_hemo, trial_name


def get_hemoglobin_averages(raw_haemo: mne.io.Raw, trial_name: str) -> pd.DataFrame:
    """
    Extract average oxy and deoxy hemoglobin for each block and channel
    
    Parameters:
    -----------
    raw_haemo : mne.io.Raw
        Hemoglobin data (converted with beer_lambert_law)
    trial_name : str
        Name of the trial
        
    Returns:
    --------
    pd.DataFrame
        DataFrame with average oxy/deoxy hemoglobin per block/channel
    """
    # Get the data
    data = raw_haemo.get_data()  # shape: (n_channels, n_times)
    ch_names = raw_haemo.ch_names
    
    # Get event information if available
    events, event_ids = mne.events_from_annotations(raw_haemo)
    
    # Create results list
    results = []
    
    if len(events) > 0:
        # Process each event/block
        for event_idx, (event_sample, duration, event_id) in enumerate(events):
            # Get event label
            event_label = None
            for label, id_val in event_ids.items():
                if id_val == event_id:
                    event_label = label
                    break
            
            # Define block window
            block_start = event_sample
            if event_idx < len(events) - 1:
                block_end = events[event_idx + 1][0]
            else:
                block_end = len(data[0])
            
            # Extract data for this block
            block_data = data[:, block_start:block_end]
            
            # Calculate mean for each channel
            for ch_idx, ch_name in enumerate(ch_names):
                # Determine if it's HbO or HbR
                if 'hbo' in ch_name.lower():
                    hb_type = 'HbO'
                elif 'hbr' in ch_name.lower():
                    hb_type = 'HbR'
                else:
                    hb_type = 'Unknown'
                
                mean_value = np.mean(block_data[ch_idx])
                
                results.append({
                    'Trial': trial_name,
                    'Block': event_label if event_label else f'Block_{event_idx}',
                    'Channel': ch_name,
                    'HbType': hb_type,
                    'Mean_Value': mean_value,
                    'Std_Value': np.std(block_data[ch_idx]),
                    'Block_Duration_s': (block_end - block_start) / raw_haemo.info['sfreq']
                })
    else:
        # If no events, treat entire recording as one block
        for ch_idx, ch_name in enumerate(ch_names):
            if 'hbo' in ch_name.lower():
                hb_type = 'HbO'
            elif 'hbr' in ch_name.lower():
                hb_type = 'HbR'
            else:
                hb_type = 'Unknown'
            
            mean_value = np.mean(data[ch_idx])
            
            results.append({
                'Trial': trial_name,
                'Block': 'Entire_Recording',
                'Channel': ch_name,
                'HbType': hb_type,
                'Mean_Value': mean_value,
                'Std_Value': np.std(data[ch_idx]),
                'Block_Duration_s': len(data[0]) / raw_haemo.info['sfreq']
            })
    
    return pd.DataFrame(results)


def extract_source_detector(channel_name: str) -> str:
    """Extract S#_D# pattern from channel name like 'S1_D1 hbo'"""
    match = re.search(r'S(\d+)_D(\d+)', channel_name)
    if match:
        return f"S{match.group(1)}_D{match.group(2)}"
    return None


def load_channel_mapping(mapping_file: str) -> Dict[str, str]:
    """
    Load channel to brain region mapping from JSON file
    
    Parameters:
    -----------
    mapping_file : str
        Path to JSON file with channel mappings
        
    Returns:
    --------
    dict : {channel: region} mapping
    """
    with open(mapping_file, 'r') as f:
        channel_map = json.load(f)
    
    # Create lookup dictionary: "S{source}_D{detector}" -> region
    channel_to_region = {}
    for entry in channel_map:
        key = f"S{entry['source']}_D{entry['detector']}"
        channel_to_region[key] = entry['region']
    
    return channel_to_region


def process_snirf_files(input_dir: str, output_dir: str, channel_mapping_file: str = None):
    """
    Main processing pipeline: load SNIRF files, extract averages, create pivot tables and heatmaps
    
    Parameters:
    -----------
    input_dir : str
        Directory containing .snirf files
    output_dir : str
        Directory for output files (CSV and images)
    channel_mapping_file : str, optional
        Path to channel mapping JSON file
    """
    # Create output directories
    output_path = Path(output_dir)
    data_dir = output_path / "data"
    figures_dir = output_path / "figures"
    data_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all SNIRF files
    input_path = Path(input_dir)
    snirf_files = list(input_path.glob("*.snirf"))
    
    if not snirf_files:
        print(f"❌ No .snirf files found in {input_dir}")
        return
    
    print(f"\n{'='*80}")
    print(f"Found {len(snirf_files)} SNIRF files in {input_dir}")
    print(f"{'='*80}\n")
    
    # Process all SNIRF files
    all_averages = []
    all_blocks_seen = []  # Track block order across all files
    
    for snirf_file in snirf_files:
        try:
            raw_hemo, trial_name = raw_intensity_to_hemo(str(snirf_file))
            averages_df = get_hemoglobin_averages(raw_hemo, trial_name)
            
            # Collect blocks from this file in order
            file_blocks = averages_df['Block'].unique().tolist()
            
            # Add any new blocks to our master list, preserving order
            for block in file_blocks:
                if block not in all_blocks_seen:
                    all_blocks_seen.append(block)
            
            all_averages.append(averages_df)
            print(f"✓ Processed: {trial_name} ({len(averages_df)} measurements, {len(file_blocks)} blocks)\n")
        except Exception as e:
            print(f"✗ Error processing {snirf_file.name}: {e}\n")
    
    # Use all blocks found across all files
    block_order = all_blocks_seen
    if block_order:
        print(f"\nFound {len(block_order)} unique blocks across all files:")
        for i, block in enumerate(block_order, 1):
            print(f"  {i}. {block}")
        print()
    
    if not all_averages:
        print("❌ No files were successfully processed")
        return
    
    # Combine all results
    combined_df = pd.concat(all_averages, ignore_index=True)
    
    print(f"\n{'='*80}")
    print(f"Combined Results: {len(combined_df)} total measurements")
    print(f"{'='*80}\n")
    
    # Create detailed pivot table (Trial/Channel x Blocks)
    print("Creating detailed pivot table...")
    hbo_df = combined_df[combined_df['HbType'] == 'HbO'].copy()
    hbo_df['Row_Label'] = hbo_df['Trial'] + ' | ' + hbo_df['Channel'].astype(str)
    
    detailed_pivot = hbo_df.pivot_table(
        index='Row_Label',
        columns='Block',
        values='Mean_Value',
        aggfunc='mean'
    )
    
    # Reorder columns chronologically
    existing_blocks = [block for block in block_order if block in detailed_pivot.columns]
    detailed_pivot = detailed_pivot[existing_blocks]
    
    # Save detailed pivot table
    output_csv_detailed = data_dir / "hbo_averages_detailed_pivot.csv"
    detailed_pivot.to_csv(output_csv_detailed)
    print(f"✓ Saved detailed pivot table to: {output_csv_detailed}")
    print(f"  Shape: {detailed_pivot.shape[0]} rows × {detailed_pivot.shape[1]} columns\n")
    
    # Load channel mapping if provided
    if channel_mapping_file and os.path.exists(channel_mapping_file):
        print(f"Loading channel mapping from: {channel_mapping_file}")
        channel_to_region = load_channel_mapping(channel_mapping_file)
        print(f"✓ Loaded {len(channel_to_region)} channel mappings\n")
        
        # Add region information
        hbo_df_regions = combined_df[combined_df['HbType'] == 'HbO'].copy()
        hbo_df_regions['Source_Detector'] = hbo_df_regions['Channel'].apply(extract_source_detector)
        hbo_df_regions['Region'] = hbo_df_regions['Source_Detector'].map(channel_to_region)
        
        # Check for unmapped channels
        unmapped = hbo_df_regions[hbo_df_regions['Region'].isna()]
        if len(unmapped) > 0:
            print(f"⚠ Warning: {len(unmapped)} measurements with unmapped channels")
        else:
            print("✓ All channels successfully mapped to regions")
        
        # Filter out unmapped regions
        hbo_df_regions_clean = hbo_df_regions[hbo_df_regions['Region'].notna()].copy()
        unique_regions = hbo_df_regions_clean['Region'].unique()
        
        print(f"\nFound {len(unique_regions)} brain regions")
        print(f"{'='*80}\n")
        
        # Create region-based pivot tables
        region_pivots = {}
        
        for region in sorted(unique_regions):
            region_data = hbo_df_regions_clean[hbo_df_regions_clean['Region'] == region].copy()
            
            # Create pivot table: Trial (rows) x Blocks (columns)
            region_pivot = region_data.pivot_table(
                index='Trial',
                columns='Block',
                values='Mean_Value',
                aggfunc='mean'
            )
            
            # Reorder columns chronologically
            existing_blocks = [block for block in block_order if block in region_pivot.columns]
            region_pivot = region_pivot[existing_blocks]
            
            region_pivots[region] = region_pivot
            
            # Save to CSV
            safe_region_name = region.replace(' ', '_').replace('/', '_').lower()
            output_csv = data_dir / f"hbo_region_{safe_region_name}.csv"
            region_pivot.to_csv(output_csv)
            
            print(f"✓ {region}")
            print(f"  Shape: {region_pivot.shape[0]} trials × {region_pivot.shape[1]} blocks")
            print(f"  Channels averaged: {region_data['Source_Detector'].nunique()}")
            print(f"  Saved to: {output_csv.name}\n")
        
        print(f"{'='*80}")
        print(f"✓ Created {len(region_pivots)} region-based pivot tables")
        print(f"{'='*80}\n")
        
        # Create heatmaps
        print(f"Creating heatmaps for {len(region_pivots)} brain regions...")
        print(f"{'='*80}\n")
        
        for region_name, pivot_data in region_pivots.items():
            try:
                # Create figure
                fig, ax = plt.subplots(figsize=(12, 6))
                
                sns.heatmap(
                    pivot_data,
                    annot=True,
                    fmt='.2e',
                    cmap='RdYlBu_r',
                    center=0,
                    cbar_kws={'label': 'HbO Concentration Change'},
                    linewidths=0.5,
                    linecolor='gray',
                    ax=ax
                )
                
                ax.set_title(f'HbO Averages: {region_name}', fontsize=14, fontweight='bold', pad=20)
                ax.set_xlabel('Block', fontsize=12, fontweight='bold')
                ax.set_ylabel('Trial', fontsize=12, fontweight='bold')
                
                plt.xticks(rotation=45, ha='right')
                plt.yticks(rotation=0)
                plt.tight_layout()
                
                # Save figure
                safe_region_name = region_name.replace(' ', '_').replace('/', '_').lower()
                figure_path = figures_dir / f"heatmap_{safe_region_name}.png"
                plt.savefig(figure_path, dpi=300, bbox_inches='tight')
                
                print(f"✓ {region_name}")
                print(f"  Saved to: {figure_path.name}\n")
                
                plt.close()
            except Exception as e:
                print(f"✗ Error creating heatmap for {region_name}: {e}\n")
        
        print(f"{'='*80}")
        print(f"✓ Created heatmaps for {len(region_pivots)} regions")
        print(f"All outputs saved to: {output_dir}")
        print(f"{'='*80}")
    else:
        if channel_mapping_file:
            print(f"⚠ Warning: Channel mapping file not found: {channel_mapping_file}")
        print("⚠ Skipping region-based analysis and heatmaps")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Process fNIRS SNIRF files and generate hemoglobin analysis reports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process files in data/raw/ directory with default output
  %(prog)s data/raw/
  
  # Specify custom output directory
  %(prog)s data/raw/ -o results/
  
  # Include channel mapping for region-based analysis
  %(prog)s data/raw/ -o results/ -m references/nirsit_full_channel_map.json
        """
    )
    
    parser.add_argument(
        'input_dir',
        nargs='?',  # Make input_dir optional
        help='Directory containing .snirf files to process'
    )
    
    parser.add_argument(
        '-o', '--output',
        dest='output_dir',
        default='output',
        help='Output directory for processed data and figures (default: output/)'
    )
    
    parser.add_argument(
        '-m', '--mapping',
        dest='mapping_file',
        help='Path to channel mapping JSON file for region-based analysis'
    )
    
    args = parser.parse_args()
    
    # Prompt for input directory if not provided
    if not args.input_dir:
        args.input_dir = input("Enter the directory containing .snirf files: ").strip()
        if not args.input_dir:
            print("❌ Error: Input directory is required")
            sys.exit(1)
    
    # Validate input directory
    if not os.path.isdir(args.input_dir):
        print(f"❌ Error: Input directory does not exist: {args.input_dir}")
        sys.exit(1)
    
    # Prompt for mapping file if not provided
    if not args.mapping_file:
        mapping_input = input("Enter the path to channel mapping JSON file (or press Enter to skip): ").strip()
        if mapping_input:
            args.mapping_file = mapping_input
    
    # Process files
    try:
        process_snirf_files(args.input_dir, args.output_dir, args.mapping_file)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
