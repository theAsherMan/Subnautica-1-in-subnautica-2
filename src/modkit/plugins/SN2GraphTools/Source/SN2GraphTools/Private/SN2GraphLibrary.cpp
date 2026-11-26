#include "SN2GraphLibrary.h"

#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "K2Node_CallArrayFunction.h"
#include "K2Node_CallFunction.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_Event.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_MacroInstance.h"
#include "K2Node_Self.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Modules/ModuleManager.h"
#include "UObject/UnrealType.h"
#include "Blueprint/WidgetTree.h"
#include "Components/BorderSlot.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/OverlaySlot.h"
#include "Components/PanelWidget.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/Widget.h"
#include "K2Node_ComponentBoundEvent.h"
#include "WidgetBlueprint.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, SN2GraphTools);

DEFINE_LOG_CATEGORY_STATIC(LogSN2Graph, Log, All);

namespace
{
	template <typename T>
	T* Place(UEdGraph* Graph, int32 X, int32 Y, TFunctionRef<void(T*)> Setup)
	{
		if (!Graph)
		{
			return nullptr;
		}
		Graph->Modify();
		FGraphNodeCreator<T> Creator(*Graph);
		T* Node = Creator.CreateNode(false);
		Setup(Node);
		Node->NodePosX = X;
		Node->NodePosY = Y;
		Creator.Finalize();
		return Node;
	}

	UEdGraphPin* FindPinLoose(UEdGraphNode* Node, const FString& Name)
	{
		if (!Node)
		{
			return nullptr;
		}
		if (UEdGraphPin* P = Node->FindPin(FName(*Name)))
		{
			return P;
		}
		for (UEdGraphPin* P : Node->Pins)
		{
			if (P && (P->PinName.ToString().Equals(Name, ESearchCase::IgnoreCase) || P->GetDisplayName().ToString().Equals(Name, ESearchCase::IgnoreCase)))
			{
				return P;
			}
		}
		return nullptr;
	}

	UBlueprint* BlueprintOf(UEdGraph* Graph)
	{
		return Graph ? FBlueprintEditorUtils::FindBlueprintForGraph(Graph) : nullptr;
	}
}

UEdGraph* USN2GraphLibrary::GetEventGraph(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		return nullptr;
	}
	if (UEdGraph* G = FBlueprintEditorUtils::FindEventGraph(Blueprint))
	{
		return G;
	}
	UEdGraph* G = FBlueprintEditorUtils::CreateNewGraph(Blueprint, UEdGraphSchema_K2::GN_EventGraph, UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
	FBlueprintEditorUtils::AddUbergraphPage(Blueprint, G);
	return G;
}

int32 USN2GraphLibrary::ClearGraph(UEdGraph* Graph)
{
	UBlueprint* BP = BlueprintOf(Graph);
	if (!Graph || !BP)
	{
		return 0;
	}
	TArray<UEdGraphNode*> Nodes = Graph->Nodes;
	for (UEdGraphNode* N : Nodes)
	{
		if (N)
		{
			FBlueprintEditorUtils::RemoveNode(BP, N, true);
		}
	}
	return Nodes.Num();
}

UEdGraphNode* USN2GraphLibrary::AddEventOverride(UBlueprint* Blueprint, UEdGraph* Graph, FName EventName, int32 X, int32 Y)
{
	if (!Blueprint || !Blueprint->ParentClass)
	{
		return nullptr;
	}
	UFunction* Fn = Blueprint->ParentClass->FindFunctionByName(EventName);
	if (!Fn)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("AddEventOverride: %s not found on %s"), *EventName.ToString(), *Blueprint->ParentClass->GetName());
		return nullptr;
	}
	UClass* Owner = Fn->GetOwnerClass();
	return Place<UK2Node_Event>(Graph, X, Y, [&](UK2Node_Event* N)
	{
		N->EventReference.SetExternalMember(EventName, Owner);
		N->bOverrideFunction = true;
	});
}

UEdGraphNode* USN2GraphLibrary::AddCustomEvent(UEdGraph* Graph, FName EventName, int32 X, int32 Y)
{
	return Place<UK2Node_CustomEvent>(Graph, X, Y, [&](UK2Node_CustomEvent* N)
	{
		N->CustomFunctionName = EventName;
	});
}

UEdGraphNode* USN2GraphLibrary::AddCallFunction(UEdGraph* Graph, UClass* FunctionOwner, FName FunctionName, int32 X, int32 Y)
{
	UFunction* Fn = FunctionOwner ? FunctionOwner->FindFunctionByName(FunctionName) : nullptr;
	if (!Fn)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("AddCallFunction: %s not found on %s"), *FunctionName.ToString(), FunctionOwner ? *FunctionOwner->GetName() : TEXT("null"));
		return nullptr;
	}
	// KismetArrayLibrary functions use wildcard array pins and need the array-aware node class.
	if (Fn->GetOwnerClass() && Fn->GetOwnerClass()->GetFName() == FName(TEXT("KismetArrayLibrary")))
	{
		return Place<UK2Node_CallArrayFunction>(Graph, X, Y, [&](UK2Node_CallArrayFunction* N)
		{
			N->SetFromFunction(Fn);
		});
	}
	return Place<UK2Node_CallFunction>(Graph, X, Y, [&](UK2Node_CallFunction* N)
	{
		N->SetFromFunction(Fn);
	});
}

UEdGraphNode* USN2GraphLibrary::AddStandardMacro(UEdGraph* Graph, FName MacroName, int32 X, int32 Y)
{
	UBlueprint* Macros = LoadObject<UBlueprint>(nullptr, TEXT("/Engine/EditorBlueprintResources/StandardMacros.StandardMacros"));
	if (!Macros)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("StandardMacros not found"));
		return nullptr;
	}
	UEdGraph* Macro = nullptr;
	for (UEdGraph* G : Macros->MacroGraphs)
	{
		if (G && G->GetFName() == MacroName)
		{
			Macro = G;
			break;
		}
	}
	if (!Macro)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("macro %s not found"), *MacroName.ToString());
		return nullptr;
	}
	return Place<UK2Node_MacroInstance>(Graph, X, Y, [&](UK2Node_MacroInstance* N)
	{
		N->SetMacroGraph(Macro);
	});
}

UEdGraphNode* USN2GraphLibrary::AddBranch(UEdGraph* Graph, int32 X, int32 Y)
{
	return Place<UK2Node_IfThenElse>(Graph, X, Y, [](UK2Node_IfThenElse*) {});
}

UEdGraphNode* USN2GraphLibrary::AddSequence(UEdGraph* Graph, int32 NumOutputs, int32 X, int32 Y)
{
	UK2Node_ExecutionSequence* N = Place<UK2Node_ExecutionSequence>(Graph, X, Y, [](UK2Node_ExecutionSequence*) {});
	if (N)
	{
		int32 Outputs = 0;
		for (UEdGraphPin* P : N->Pins)
		{
			if (P && P->Direction == EGPD_Output)
			{
				++Outputs;
			}
		}
		for (; Outputs < NumOutputs; ++Outputs)
		{
			N->AddInputPin();
		}
	}
	return N;
}

UEdGraphNode* USN2GraphLibrary::AddSelf(UEdGraph* Graph, int32 X, int32 Y)
{
	return Place<UK2Node_Self>(Graph, X, Y, [](UK2Node_Self*) {});
}

bool USN2GraphLibrary::AddMemberVariable(UBlueprint* Blueprint, FName Name, FName PinCategory, FName PinSubCategory, UObject* SubCategoryObject, bool bIsArray, const FString& DefaultValue)
{
	if (!Blueprint)
	{
		return false;
	}
	if (FBlueprintEditorUtils::FindNewVariableIndex(Blueprint, Name) != INDEX_NONE)
	{
		FBlueprintEditorUtils::RemoveMemberVariable(Blueprint, Name);
	}
	FEdGraphPinType Type;
	Type.PinCategory = PinCategory;
	Type.PinSubCategory = PinSubCategory;
	Type.PinSubCategoryObject = SubCategoryObject;
	Type.ContainerType = bIsArray ? EPinContainerType::Array : EPinContainerType::None;
	return FBlueprintEditorUtils::AddMemberVariable(Blueprint, Name, Type, DefaultValue);
}

UEdGraphNode* USN2GraphLibrary::AddVariableNode(UBlueprint* Blueprint, UEdGraph* Graph, FName Name, bool bSetter, int32 X, int32 Y)
{
	if (bSetter)
	{
		return Place<UK2Node_VariableSet>(Graph, X, Y, [&](UK2Node_VariableSet* N)
		{
			N->VariableReference.SetSelfMember(Name);
		});
	}
	return Place<UK2Node_VariableGet>(Graph, X, Y, [&](UK2Node_VariableGet* N)
	{
		N->VariableReference.SetSelfMember(Name);
	});
}

bool USN2GraphLibrary::SetPinDefault(UEdGraphNode* Node, const FString& PinName, const FString& Value)
{
	UEdGraphPin* Pin = FindPinLoose(Node, PinName);
	if (!Pin)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("SetPinDefault: no pin %s on %s"), *PinName, Node ? *Node->GetName() : TEXT("null"));
		return false;
	}
	GetDefault<UEdGraphSchema_K2>()->TrySetDefaultValue(*Pin, Value);
	return true;
}

bool USN2GraphLibrary::SetPinDefaultObject(UEdGraphNode* Node, const FString& PinName, UObject* Object)
{
	UEdGraphPin* Pin = FindPinLoose(Node, PinName);
	if (!Pin)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("SetPinDefaultObject: no pin %s on %s"), *PinName, Node ? *Node->GetName() : TEXT("null"));
		return false;
	}
	GetDefault<UEdGraphSchema_K2>()->TrySetDefaultObject(*Pin, Object);
	return true;
}

bool USN2GraphLibrary::Connect(UEdGraphNode* From, const FString& FromPin, UEdGraphNode* To, const FString& ToPin, FString& OutMessage)
{
	UEdGraphPin* A = FindPinLoose(From, FromPin);
	UEdGraphPin* B = FindPinLoose(To, ToPin);
	if (!A || !B)
	{
		OutMessage = FString::Printf(TEXT("pin not found: %s.%s=%s, %s.%s=%s"),
			From ? *From->GetName() : TEXT("null"), *FromPin, A ? TEXT("ok") : TEXT("MISSING"),
			To ? *To->GetName() : TEXT("null"), *ToPin, B ? TEXT("ok") : TEXT("MISSING"));
		return false;
	}
	const UEdGraphSchema_K2* K2 = GetDefault<UEdGraphSchema_K2>();
	const FPinConnectionResponse R = K2->CanCreateConnection(A, B);
	OutMessage = R.Message.ToString();
	if (R.Response == CONNECT_RESPONSE_DISALLOW)
	{
		return false;
	}
	return K2->TryCreateConnection(A, B);
}

TArray<FString> USN2GraphLibrary::DescribePins(UEdGraphNode* Node)
{
	TArray<FString> Out;
	if (!Node)
	{
		return Out;
	}
	for (UEdGraphPin* P : Node->Pins)
	{
		if (!P)
		{
			continue;
		}
		Out.Add(FString::Printf(TEXT("%s %s : %s/%s(%s)%s [%s]"),
			P->Direction == EGPD_Input ? TEXT("in ") : TEXT("out"),
			*P->PinName.ToString(),
			*P->PinType.PinCategory.ToString(),
			*P->PinType.PinSubCategory.ToString(),
			P->PinType.PinSubCategoryObject.IsValid() ? *P->PinType.PinSubCategoryObject->GetName() : TEXT(""),
			P->PinType.IsArray() ? TEXT("[]") : TEXT(""),
			*P->GetDefaultAsString()));
	}
	return Out;
}

bool USN2GraphLibrary::CompileWithLog(UBlueprint* Blueprint, TArray<FString>& OutMessages)
{
	if (!Blueprint)
	{
		return false;
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	FCompilerResultsLog Log;
	Log.bSilentMode = true;
	FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::None, &Log);
	for (const TSharedRef<FTokenizedMessage>& M : Log.Messages)
	{
		OutMessages.Add(M->ToText().ToString());
	}
	return Blueprint->Status != BS_Error;
}

namespace
{
	FArrayProperty* FindObjectArrayProperty(UObject* Object, FName PropertyName)
	{
		if (!Object)
		{
			return nullptr;
		}
		FArrayProperty* Arr = CastField<FArrayProperty>(FindFProperty<FProperty>(Object->GetClass(), PropertyName));
		if (!Arr || !CastField<FObjectPropertyBase>(Arr->Inner))
		{
			return nullptr;
		}
		return Arr;
	}
}

TArray<FString> USN2GraphLibrary::DescribeObjectArray(UObject* Object, FName PropertyName)
{
	TArray<FString> Out;
	FArrayProperty* Arr = FindObjectArrayProperty(Object, PropertyName);
	if (!Arr)
	{
		Out.Add(FString::Printf(TEXT("MISSING %s"), *PropertyName.ToString()));
		return Out;
	}
	FObjectPropertyBase* Inner = CastField<FObjectPropertyBase>(Arr->Inner);
	FScriptArrayHelper Helper(Arr, Arr->ContainerPtrToValuePtr<void>(Object));
	for (int32 i = 0; i < Helper.Num(); ++i)
	{
		UObject* E = Inner->GetObjectPropertyValue(Helper.GetRawPtr(i));
		Out.Add(FString::Printf(TEXT("%d %s outer=%s"), i,
			E ? *E->GetPathName() : TEXT("None"),
			(E && E->GetOuter()) ? *E->GetOuter()->GetPathName() : TEXT("None")));
	}
	return Out;
}

int32 USN2GraphLibrary::ClearObjectArray(UObject* Object, FName PropertyName)
{
	FArrayProperty* Arr = FindObjectArrayProperty(Object, PropertyName);
	if (!Arr)
	{
		return -1;
	}
	Object->Modify();
	FScriptArrayHelper Helper(Arr, Arr->ContainerPtrToValuePtr<void>(Object));
	const int32 N = Helper.Num();
	Helper.EmptyValues();
	return N;
}

void USN2GraphLibrary::NotifyPropertyChanged(UObject* Object, FName PropertyName)
{
	if (!Object)
	{
		return;
	}
	FProperty* Prop = FindFProperty<FProperty>(Object->GetClass(), PropertyName);
	if (!Prop)
	{
		return;
	}
	Object->PreEditChange(Prop);
	FPropertyChangedEvent Ev(Prop, EPropertyChangeType::ValueSet);
	Object->PostEditChangeProperty(Ev);
}

// ---- UMG widget blueprint building ----

UWidget* USN2GraphLibrary::AddWidget(UBlueprint* WidgetBlueprint, UClass* WidgetClass, FName Name, UWidget* Parent)
{
	UWidgetBlueprint* WBP = Cast<UWidgetBlueprint>(WidgetBlueprint);
	if (!WBP || !WBP->WidgetTree || !WidgetClass || !WidgetClass->IsChildOf(UWidget::StaticClass()))
	{
		return nullptr;
	}
	WBP->Modify();
	UWidget* W = WBP->WidgetTree->ConstructWidget<UWidget>(WidgetClass, Name);
	if (!W)
	{
		return nullptr;
	}
	if (!Parent)
	{
		if (WBP->WidgetTree->RootWidget)
		{
			UE_LOG(LogSN2Graph, Warning, TEXT("AddWidget %s: root already exists"), *Name.ToString());
			return nullptr;
		}
		WBP->WidgetTree->RootWidget = W;
	}
	else
	{
		UPanelWidget* P = Cast<UPanelWidget>(Parent);
		if (!P || !P->AddChild(W))
		{
			UE_LOG(LogSN2Graph, Warning, TEXT("AddWidget %s: parent %s cannot take a child"), *Name.ToString(), *Parent->GetName());
			return nullptr;
		}
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WBP);
	return W;
}

UWidget* USN2GraphLibrary::FindWidget(UBlueprint* WidgetBlueprint, FName Name)
{
	UWidgetBlueprint* WBP = Cast<UWidgetBlueprint>(WidgetBlueprint);
	return (WBP && WBP->WidgetTree) ? WBP->WidgetTree->FindWidget(Name) : nullptr;
}

bool USN2GraphLibrary::SetWidgetIsVariable(UWidget* Widget, bool bIsVariable)
{
	if (!Widget)
	{
		return false;
	}
	Widget->Modify();
	Widget->bIsVariable = bIsVariable;
	return true;
}

bool USN2GraphLibrary::SetCanvasSlot(UWidget* Widget, FVector2D AnchorMin, FVector2D AnchorMax, FVector2D Position, FVector2D Size, FVector2D Alignment, int32 ZOrder)
{
	UCanvasPanelSlot* S = Widget ? Cast<UCanvasPanelSlot>(Widget->Slot) : nullptr;
	if (!S)
	{
		return false;
	}
	S->Modify();
	S->SetAnchors(FAnchors(AnchorMin.X, AnchorMin.Y, AnchorMax.X, AnchorMax.Y));
	S->SetPosition(Position);
	S->SetSize(Size);
	S->SetAlignment(Alignment);
	S->SetZOrder(ZOrder);
	return true;
}

bool USN2GraphLibrary::SetBoxSlot(UWidget* Widget, FMargin Padding, float FillValue, int32 HAlign, int32 VAlign)
{
	if (!Widget || !Widget->Slot)
	{
		return false;
	}
	const EHorizontalAlignment H = HAlign == 1 ? HAlign_Left : HAlign == 2 ? HAlign_Center : HAlign == 3 ? HAlign_Right : HAlign_Fill;
	const EVerticalAlignment V = VAlign == 1 ? VAlign_Top : VAlign == 2 ? VAlign_Center : VAlign == 3 ? VAlign_Bottom : VAlign_Fill;
	FSlateChildSize Size = FillValue > 0.f ? FSlateChildSize(ESlateSizeRule::Fill) : FSlateChildSize(ESlateSizeRule::Automatic);
	Size.Value = FillValue > 0.f ? FillValue : 1.f;
	Widget->Slot->Modify();
	if (UVerticalBoxSlot* VS = Cast<UVerticalBoxSlot>(Widget->Slot))
	{
		VS->SetPadding(Padding); VS->SetHorizontalAlignment(H); VS->SetVerticalAlignment(V); VS->SetSize(Size);
		return true;
	}
	if (UHorizontalBoxSlot* HS = Cast<UHorizontalBoxSlot>(Widget->Slot))
	{
		HS->SetPadding(Padding); HS->SetHorizontalAlignment(H); HS->SetVerticalAlignment(V); HS->SetSize(Size);
		return true;
	}
	if (UOverlaySlot* OS = Cast<UOverlaySlot>(Widget->Slot))
	{
		OS->SetPadding(Padding); OS->SetHorizontalAlignment(H); OS->SetVerticalAlignment(V);
		return true;
	}
	if (UBorderSlot* BS = Cast<UBorderSlot>(Widget->Slot))
	{
		BS->SetPadding(Padding); BS->SetHorizontalAlignment(H); BS->SetVerticalAlignment(V);
		return true;
	}
	return false;
}

TArray<FString> USN2GraphLibrary::DescribeWidgetTree(UBlueprint* WidgetBlueprint)
{
	TArray<FString> Out;
	UWidgetBlueprint* WBP = Cast<UWidgetBlueprint>(WidgetBlueprint);
	if (!WBP || !WBP->WidgetTree)
	{
		Out.Add(TEXT("MISSING widget tree"));
		return Out;
	}
	TFunction<void(UWidget*, int32)> Walk = [&](UWidget* W, int32 Depth)
	{
		if (!W)
		{
			return;
		}
		Out.Add(FString::Printf(TEXT("%d %s : %s var=%d parent=%s slot=%s"), Depth, *W->GetName(), *W->GetClass()->GetName(), W->bIsVariable ? 1 : 0,
			W->GetParent() ? *W->GetParent()->GetName() : TEXT("-"), W->Slot ? *W->Slot->GetClass()->GetName() : TEXT("-")));
		if (UPanelWidget* P = Cast<UPanelWidget>(W))
		{
			for (int32 i = 0; i < P->GetChildrenCount(); ++i)
			{
				Walk(P->GetChildAt(i), Depth + 1);
			}
		}
	};
	Walk(WBP->WidgetTree->RootWidget, 0);
	return Out;
}

UEdGraphNode* USN2GraphLibrary::AddWidgetBoundEvent(UBlueprint* WidgetBlueprint, FName WidgetName, FName DelegateName, FString& OutMessage)
{
	UWidgetBlueprint* WBP = Cast<UWidgetBlueprint>(WidgetBlueprint);
	UWidget* W = FindWidget(WidgetBlueprint, WidgetName);
	if (!WBP || !W)
	{
		OutMessage = TEXT("widget not found");
		return nullptr;
	}
	FKismetEditorUtilities::CompileBlueprint(WBP);
	FObjectProperty* Prop = WBP->SkeletonGeneratedClass ? FindFProperty<FObjectProperty>(WBP->SkeletonGeneratedClass, WidgetName) : nullptr;
	if (!Prop)
	{
		Prop = WBP->GeneratedClass ? FindFProperty<FObjectProperty>(WBP->GeneratedClass, WidgetName) : nullptr;
	}
	if (!Prop)
	{
		OutMessage = TEXT("no member variable for widget (is it IsVariable and compiled?)");
		return nullptr;
	}
	if (!FindFProperty<FMulticastDelegateProperty>(W->GetClass(), DelegateName))
	{
		OutMessage = TEXT("delegate not found on widget class");
		return nullptr;
	}
	if (const UK2Node_ComponentBoundEvent* Existing = FKismetEditorUtilities::FindBoundEventForComponent(WBP, DelegateName, WidgetName))
	{
		OutMessage = TEXT("already existed");
		return const_cast<UK2Node_ComponentBoundEvent*>(Existing);
	}
	FKismetEditorUtilities::CreateNewBoundEventForClass(W->GetClass(), DelegateName, WBP, Prop);
	const UK2Node_ComponentBoundEvent* N = FKismetEditorUtilities::FindBoundEventForComponent(WBP, DelegateName, WidgetName);
	OutMessage = N ? TEXT("ok") : TEXT("CreateNewBoundEventForClass produced no node");
	return const_cast<UK2Node_ComponentBoundEvent*>(N);
}
