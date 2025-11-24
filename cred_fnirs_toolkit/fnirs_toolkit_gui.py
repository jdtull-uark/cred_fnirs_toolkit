#!/usr/bin/env python3
"""
fNIRS Toolkit GUI - Process SNIRF files and generate hemoglobin analysis reports
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
from pathlib import Path
import os

# Import the processing function from CLI
from fnirs_toolkit_cli import process_snirf_files


class FNIRSToolkitGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("fNIRS Toolkit GUI")
        self.root.geometry("800x600")
        
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar(value="output")
        self.mapping_file = tk.StringVar()
        
        self.create_widgets()
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        title_label = ttk.Label(main_frame, text="fNIRS SNIRF File Processor", 
                               font=('Helvetica', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Input Directory
        ttk.Label(main_frame, text="Input Directory:", font=('Helvetica', 10, 'bold')).grid(
            row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.input_dir, width=50).grid(
            row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_input).grid(
            row=1, column=2, pady=5)
        ttk.Label(main_frame, text="Directory containing .snirf files", 
                 font=('Helvetica', 8), foreground='gray').grid(
            row=2, column=1, sticky=tk.W, padx=5)
        
        # Output Directory
        ttk.Label(main_frame, text="Output Directory:", font=('Helvetica', 10, 'bold')).grid(
            row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_dir, width=50).grid(
            row=3, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_output).grid(
            row=3, column=2, pady=5)
        ttk.Label(main_frame, text="Where to save processed data and figures", 
                 font=('Helvetica', 8), foreground='gray').grid(
            row=4, column=1, sticky=tk.W, padx=5)
        
        # Channel Mapping File (Optional)
        ttk.Label(main_frame, text="Channel Mapping:", font=('Helvetica', 10, 'bold')).grid(
            row=5, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.mapping_file, width=50).grid(
            row=5, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_mapping).grid(
            row=5, column=2, pady=5)
        ttk.Label(main_frame, text="JSON file for region-based analysis (optional)", 
                 font=('Helvetica', 8), foreground='gray').grid(
            row=6, column=1, sticky=tk.W, padx=5)
        
        # Progress/Output Area
        ttk.Label(main_frame, text="Output:", font=('Helvetica', 10, 'bold')).grid(
            row=7, column=0, sticky=tk.W, pady=(20, 5))
        
        self.output_text = scrolledtext.ScrolledText(main_frame, height=15, width=70, 
                                                      wrap=tk.WORD, state='disabled')
        self.output_text.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), 
                             pady=5)
        
        # Buttons Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=9, column=0, columnspan=3, pady=20)
        
        self.process_button = ttk.Button(button_frame, text="Run", 
                                         command=self.process_files, style='Accent.TButton')
        self.process_button.grid(row=0, column=0, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=10, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
    def browse_input(self):
        """Browse for input directory containing .snirf files"""
        directory = filedialog.askdirectory(title="Select Input Directory with SNIRF files")
        if directory:
            self.input_dir.set(directory)
            self.log(f"Input directory set: {directory}\n")
    
    def browse_output(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)
            self.log(f"Output directory set: {directory}\n")
    
    def browse_mapping(self):
        """Browse for channel mapping JSON file"""
        filename = filedialog.askopenfilename(
            title="Select Channel Mapping JSON File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.mapping_file.set(filename)
            self.log(f"Channel mapping file set: {filename}\n")
    
    def log(self, message):
        """Add message to output text area"""
        self.output_text.config(state='normal')
        self.output_text.insert(tk.END, message)
        self.output_text.see(tk.END)
        self.output_text.config(state='disabled')
        self.root.update_idletasks()
    
    def clear_output(self):
        """Clear the output text area"""
        self.output_text.config(state='normal')
        self.output_text.delete(1.0, tk.END)
        self.output_text.config(state='disabled')
    
    def validate_inputs(self):
        """Validate user inputs before processing"""
        input_dir = self.input_dir.get().strip()
        
        if not input_dir:
            messagebox.showerror("Error", "Please select an input directory")
            return False
        
        if not os.path.isdir(input_dir):
            messagebox.showerror("Error", f"Input directory does not exist:\n{input_dir}")
            return False
        
        # Check if there are any .snirf files
        snirf_files = list(Path(input_dir).glob("*.snirf"))
        if not snirf_files:
            messagebox.showerror("Error", f"No .snirf files found in:\n{input_dir}")
            return False
        
        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please specify an output directory")
            return False
        
        # Check mapping file
        mapping_file = self.mapping_file.get().strip()
        if mapping_file and not os.path.isfile(mapping_file):
            result = messagebox.askyesno(
                "Warning", 
                f"Channel mapping file does not exist:\n{mapping_file}\n\n"
                "Continue without region-based analysis?"
            )
            if not result:
                return False
            # Clear the mapping file if user wants to continue
            self.mapping_file.set("")
        
        return True
    
    def process_files_thread(self):
        """Run the processing in a separate thread"""
        try:
            input_dir = self.input_dir.get().strip()
            output_dir = self.output_dir.get().strip()
            mapping_file = self.mapping_file.get().strip() or None
            
            # Redirect stdout to capture print statements
            class OutputRedirector:
                def __init__(self, log_func):
                    self.log_func = log_func
                
                def write(self, message):
                    if message.strip():
                        self.log_func(message)
                
                def flush(self):
                    pass
            
            old_stdout = sys.stdout
            sys.stdout = OutputRedirector(self.log)
            
            try:
                process_snirf_files(input_dir, output_dir, mapping_file)
                self.log("\n" + "="*80 + "\n")
                self.log("✓ Processing completed successfully!\n")
                self.log("="*80 + "\n")
                
                messagebox.showinfo("Success", "Processing completed successfully!")
            finally:
                sys.stdout = old_stdout
                
        except Exception as e:
            self.log(f"\nError: {e}\n")
            messagebox.showerror("Error", f"Processing failed:\n{str(e)}")
        finally:
            self.progress.stop()
            self.process_button.config(state='normal')
    
    def process_files(self):
        """Start processing SNIRF files"""
        if not self.validate_inputs():
            return
        
        self.clear_output()
        
        self.process_button.config(state='disabled')
        self.progress.start()
        
        self.log("Starting processing...\n")
        self.log("="*80 + "\n")
        
        # Run processing in separate thread
        thread = threading.Thread(target=self.process_files_thread, daemon=True)
        thread.start()


def main():
    """GUI entry point"""
    root = tk.Tk()
    
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    app = FNIRSToolkitGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
